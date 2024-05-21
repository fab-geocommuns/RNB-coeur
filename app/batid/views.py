import os
import uuid
from datetime import datetime

from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.urls import re_path
from revproxy.views import ProxyView

from app.celery import app as celery_app
from batid.models import Building
from batid.models import Contribution


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
                "review_comment": contribution.review_comment,
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
                building.event_type = "delete"
                building.is_active = False
                building.event_id = uuid.uuid4()
                building.event_user = request.user
                building.event_origin = {
                    "source": "contribution",
                    "contribution_id": contribution_id,
                }
                building.save()

                contribution.status = "fixed"
                contribution.status_changed_at = datetime.now()
                contribution.review_comment = review_comment
                contribution.review_user = request.user
                contribution.save()

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

            contribution.status = "refused"
            contribution.status_changed_at = datetime.now()
            contribution.review_comment = review_comment
            contribution.review_user = request.user
            contribution.save()

            return render(
                request,
                "contribution.html",
                {
                    "contribution_id": contribution_id,
                    "text": contribution.text,
                    "action_success": True,
                },
            )


def update_building_addresses(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    else:
        # check if the request is a POST request
        if request.method == "POST":
            # get the rnb_id from the request
            rnb_id = request.POST.get("rnb_id")
            contribution_id = request.POST.get("contribution_id")
            review_comment = request.POST.get("review_comment")
            addresses_id = request.POST.get("addresses_id").split(",")
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
                    building.event_type = "update"
                    building.event_id = uuid.uuid4()
                    building.event_user = request.user
                    building.event_origin = {
                        "source": "contribution",
                        "contribution_id": contribution_id,
                    }
                    building.addresses_id = addresses_id
                    building.save()

                    contribution.status = "fixed"
                    contribution.status_changed_at = datetime.now()
                    contribution.review_comment = review_comment
                    contribution.review_user = request.user
                    contribution.save()
            except Exception as e:
                return HttpResponseBadRequest("Erreur : " + str(e))

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
