import csv
import os
from io import StringIO

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import re_path
from revproxy.views import ProxyView  # type: ignore[import-untyped]

from app.celery import app as celery_app
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
