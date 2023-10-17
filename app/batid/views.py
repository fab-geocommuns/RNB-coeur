from django.shortcuts import render
from app.celery import app as celery_app
from django.contrib.auth.mixins import UserPassesTestMixin
from revproxy.views import ProxyView
from django.urls import re_path
import os

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
