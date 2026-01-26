import csv
import os
from io import StringIO

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import re_path
from revproxy.views import ProxyView  # type: ignore[import-untyped]

from app.celery import app as celery_app
from batid.exceptions import BANAPIDown
from batid.exceptions import BANUnknownCleInterop
from batid.forms import RollbackForm
from batid.models import Building
from batid.models import Contribution
from batid.services.ads import export_format as ads_export_format
from batid.services.contributions import export_format as contrib_export_format
from batid.services.rollback import rollback as rollback_service
from batid.services.rollback import rollback_dry_run


def worker(request):
    i = celery_app.control.inspect()
    active_tasks = i.active()

    return render(
        request,
        "admin/tasks.html",
        {
            "active_tasks": active_tasks,
        },
    )


@staff_member_required
def export_ads(request):

    data = ads_export_format()

    csv_f = StringIO()
    csv_writer = csv.DictWriter(csv_f, fieldnames=data[0].keys())
    csv_writer.writeheader()
    csv_writer.writerows(data)
    csv_f.seek(0)

    return HttpResponse(
        csv_f,
        content_type="text/csv",
        status=200,
        headers={"Content-Disposition": 'attachment; filename="export_ads.csv"'},
    )


@staff_member_required
def export_contributions(request):

    data = contrib_export_format()

    csv_f = StringIO()
    csv_writer = csv.DictWriter(csv_f, fieldnames=data[0].keys())
    csv_writer.writeheader()
    csv_writer.writerows(data)
    csv_f.seek(0)

    return HttpResponse(
        csv_f,
        content_type="text/csv",
        status=200,
        headers={
            "Content-Disposition": 'attachment; filename="export_contributions.csv"'
        },
    )


class FlowerProxyView(UserPassesTestMixin, ProxyView):
    # `flower` is Docker container, you can use `localhost` instead

    upstream = "http://flower:{}".format(os.environ.get("FLOWER_PORT", "5555"))

    url_prefix = "flower"
    rewrite = ((r"^/{}$".format(url_prefix), r"/{}/".format(url_prefix)),)

    def test_func(self):
        return self.request.user.is_superuser

    @classmethod
    def as_url(cls):
        return re_path(r"^(?P<path>{}.*)$".format(cls.url_prefix), cls.as_view())


class MetabaseProxyView(UserPassesTestMixin, ProxyView):
    upstream = "http://metabase:{}".format(os.environ.get("METABASE_PORT", "3000"))
    add_x_forwarded = True
    allowed_urls = [
        "/metabase/public/dashboard/",  # HTML pages of public dashboards
        "/metabase/public/question/",  # HTML pages of public questions
        "/metabase/app/",  # Static resources of metabase (JS scripts)
        "/metabase/api/session/properties",  # App properties
        "/metabase/api/public/",  # Public APIs
        "/metabase/api/geojson/",  # For the edition's map on stat page
    ]

    def test_func(self):
        if any(
            self.request.path.startswith(allowed_url)
            for allowed_url in self.allowed_urls
        ):
            return True
        return self.request.user.is_superuser

    def get_request_headers(self):
        headers = super().get_request_headers()
        if self.request.user.is_authenticated:
            headers["X-Remote-User"] = self.request.user.email
        return headers

    def dispatch(self, request, *args, **kwargs):
        kwargs["path"] = kwargs.get("path") or ""
        if kwargs["path"].startswith("/"):
            kwargs["path"] = kwargs["path"][1:]
        return super().dispatch(request, *args, **kwargs)

    @classmethod
    def as_url(cls):
        return re_path(r"^metabase(?P<path>/.*)?$", cls.as_view())


def contribution(request, contribution_id):
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    else:
        contribution = Contribution.objects.get(id=contribution_id)
        building = Building.objects.get(rnb_id=contribution.rnb_id)

        return render(
            request,
            "contribution.html",
            {
                "contribution_id": contribution_id,
                "rnb_id": contribution.rnb_id,
                "text": contribution.text,
                # join the addresses_id list to a string
                "addresses_id": ",".join(building.addresses_id),
                "addresses_id_array": building.addresses_id,
                "review_comment": contribution.review_comment,
                "coordinates": building.point.coords,
                "status": building.status,
            },
        )


def delete_building(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    else:
        # check if the request is a POST request
        if request.method == "POST":
            # get the rnb_id from the request
            rnb_id = request.POST.get("rnb_id")
            contribution_id = request.POST.get("contribution_id")
            review_comment = request.POST.get("review_comment")
            contribution = get_object_or_404(Contribution, id=contribution_id)

            if contribution.status != "pending":
                return HttpResponseBadRequest("Contribution is not pending.")
            # get the building with the rnb_id
            building = get_object_or_404(Building, rnb_id=rnb_id)

            if not building.is_active:
                return HttpResponseBadRequest("Cannot delete an inactive building.")
            # start a transaction
            with transaction.atomic():
                building.deactivate(
                    request.user,
                    {"source": "contribution", "contribution_id": contribution_id},
                )
                contribution.fix(request.user, review_comment)

            return render(
                request,
                "contribution.html",
                {
                    "contribution_id": contribution_id,
                    "rnb_id": contribution.rnb_id,
                    "text": contribution.text,
                    "action_success": True,
                },
            )


def refuse_contribution(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    else:
        # check if the request is a POST request
        if request.method == "POST":
            contribution_id = request.POST.get("contribution_id")
            review_comment = request.POST.get("review_comment")
            contribution = get_object_or_404(Contribution, id=contribution_id)

            if contribution.status != "pending":
                return HttpResponseBadRequest("Contribution is not pending.")

            contribution.refuse(request.user, review_comment)

            return render(
                request,
                "contribution.html",
                {
                    "contribution_id": contribution_id,
                    "text": contribution.text,
                    "action_success": True,
                },
            )


def update_building(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    else:
        # check if the request is a POST request
        if request.method == "POST":
            # get the rnb_id from the request
            rnb_id = request.POST.get("rnb_id")
            contribution_id = request.POST.get("contribution_id")
            review_comment = request.POST.get("review_comment")
            addresses_id_string = request.POST.get("addresses_id")
            addresses_id = addresses_id_string.split(",") if addresses_id_string else []
            status = request.POST.get("status")
            contribution = get_object_or_404(Contribution, id=contribution_id)

            if contribution.status != "pending":
                return HttpResponseBadRequest("Contribution is not pending.")
            # get the building with the rnb_id
            building = get_object_or_404(Building, rnb_id=rnb_id)

            if not building.is_active:
                return HttpResponseBadRequest("Cannot update an inactive building.")
            # start a transaction
            try:
                with transaction.atomic():
                    building.update(
                        request.user,
                        {
                            "source": "contribution",
                            "contribution_id": contribution_id,
                        },
                        status,
                        addresses_id,
                    )

                    contribution.fix(request.user, review_comment)
            except BANAPIDown as e:
                return HttpResponseBadRequest(
                    "Could not update the building. There is a new address to save but BAN API is currently down."
                )
            except BANUnknownCleInterop as e:
                return HttpResponseBadRequest(
                    "Could not update the building. The given clé d'interopérabilité was not found on the BAN API."
                )
            except Exception as e:
                return HttpResponseBadRequest("Could not update the building.")

            return render(
                request,
                "contribution.html",
                {
                    "contribution_id": contribution_id,
                    "rnb_id": contribution.rnb_id,
                    "text": contribution.text,
                    "action_success": True,
                },
            )


def merge_buildings(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    else:
        # check if the request is a POST request
        if request.method == "POST":
            # get the rnb_id from the request
            rnb_ids_string = request.POST.get("rnb_ids")
            rnb_ids = rnb_ids_string.split(",")

            contribution_id = request.POST.get("contribution_id")
            review_comment = request.POST.get("review_comment")

            merge_addresses = request.POST.get("merge_addresses")
            addresses_id = []
            if not merge_addresses:
                addresses_id_string = request.POST.get("addresses_id")
                addresses_id = (
                    addresses_id_string.split(",") if addresses_id_string else []
                )

            status = request.POST.get("status")

            contribution = get_object_or_404(Contribution, id=contribution_id)

            if contribution.status != "pending":
                return HttpResponseBadRequest("Contribution is not pending.")

            # get the buildings with given rnb_ids
            buildings = []
            for rnb_id in rnb_ids:
                building = get_object_or_404(Building, rnb_id=rnb_id)
                if not building.is_active:
                    return HttpResponseBadRequest(
                        f"Cannot update an inactive building ({building.rnb_id})."
                    )
                buildings.append(building)

            if len(buildings) < 2:
                return HttpResponseBadRequest("Not enough buildings to merge.")

            try:

                if merge_addresses:
                    # merge the existing addresses, remove duplicates
                    addresses_id = list(
                        set(
                            [
                                address
                                for building in buildings
                                for address in building.addresses_id
                            ]
                        )
                    )
                with transaction.atomic():
                    Building.merge(
                        buildings,
                        request.user,
                        {
                            "source": "contribution",
                            "contribution_id": contribution_id,
                        },
                        status,
                        addresses_id,
                    )
                    contribution.fix(request.user, review_comment)
            except Exception as e:
                return HttpResponseBadRequest(
                    "Could not merge. Most likely because the shapes of the merged buildings are not contiguous."
                )

            return render(
                request,
                "contribution.html",
                {
                    "contribution_id": contribution_id,
                    "action_success": True,
                },
            )


def superuser_required(view_func):
    decorated_view = user_passes_test(lambda u: u.is_superuser)(view_func)
    return decorated_view


@superuser_required
def rollback_view(request):
    results = None
    is_dry_run = False

    if request.method == "POST":
        form = RollbackForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data["user"]
            start_time = form.cleaned_data["start_time"]
            end_time = form.cleaned_data["end_time"]

            if "dry_run" in request.POST:
                is_dry_run = True
                results = rollback_dry_run(user, start_time, end_time)
                messages.info(
                    request,
                    f"Dry Run pour {user.email} : {results['events_found_n']} events trouvés, "
                    f"{results['events_revertable_n']} revertables, "
                    f"{results['events_not_revertable_n']} non-revertables, "
                    f"{results['events_already_reverted_n']} déjà revertés",
                )
            elif "rollback" in request.POST:
                request.session["rollback_user_id"] = user.id
                request.session["rollback_start_time"] = (
                    start_time.isoformat() if start_time else None
                )
                request.session["rollback_end_time"] = (
                    end_time.isoformat() if end_time else None
                )
                return redirect("admin:rollback_confirm")
    else:
        form = RollbackForm()

    return render(
        request,
        "admin/rollback_form.html",
        {
            "form": form,
            "results": results,
            "is_dry_run": is_dry_run,
            "title": "Rollback des événements",
        },
    )


@superuser_required
def rollback_confirm_view(request):
    from datetime import datetime

    user_id = request.session.get("rollback_user_id")
    start_time_str = request.session.get("rollback_start_time")
    end_time_str = request.session.get("rollback_end_time")

    if not user_id:
        messages.error(request, "Session expirée. Veuillez recommencer.")
        return redirect("admin:rollback")

    user = get_object_or_404(User, id=user_id)
    start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
    end_time = datetime.fromisoformat(end_time_str) if end_time_str else None

    if request.method == "POST":
        if "confirm" in request.POST:
            results = rollback_service(user, start_time, end_time)

            del request.session["rollback_user_id"]
            if "rollback_start_time" in request.session:
                del request.session["rollback_start_time"]
            if "rollback_end_time" in request.session:
                del request.session["rollback_end_time"]

            messages.success(
                request,
                f"Rollback effectué pour {user.email} : {results['events_reverted_n']} events revertés. "
                f"DataFix ID: {results['data_fix_id']}",
            )

            return render(
                request,
                "admin/rollback_results.html",
                {
                    "results": results,
                    "is_dry_run": False,
                    "title": "Résultats du Rollback",
                },
            )
        else:
            del request.session["rollback_user_id"]
            if "rollback_start_time" in request.session:
                del request.session["rollback_start_time"]
            if "rollback_end_time" in request.session:
                del request.session["rollback_end_time"]
            return redirect("admin:rollback")

    dry_run_results = rollback_dry_run(user, start_time, end_time)

    return render(
        request,
        "admin/rollback_confirm.html",
        {
            "user": user,
            "start_time": start_time,
            "end_time": end_time,
            "dry_run_results": dry_run_results,
            "title": "Confirmation du Rollback",
        },
    )
