import csv
import os
from io import StringIO

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import transaction
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.urls import re_path
from revproxy.views import ProxyView

from app.celery import app as celery_app
from batid.models import Building
from batid.models import Contribution
from batid.services.ads import export_format as ads_export_format
from batid.services.contributions import export_format as contrib_export_format


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
                building.soft_delete(
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
            except Exception as e:
                return HttpResponseBadRequest(
                    "Could not update the building. It is likely that this address does not exist yet in our database."
                )

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
