"""app URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include
from django.urls import path

from app.debug_views import test_error
from batid.views import contribution
from batid.views import delete_building
from batid.views import FlowerProxyView
from batid.views import merge_buildings
from batid.views import MetabaseProxyView
from batid.views import refuse_contribution
from batid.views import update_building

urlpatterns = [
    path("", include("website.urls")),
    path("api/alpha/", include("api_alpha.urls")),
    path("admin/", admin.site.urls),
    FlowerProxyView.as_url(),
    MetabaseProxyView.as_url(),
    path("contribution/fix/<int:contribution_id>", contribution),
    path("contribution/fix/delete", delete_building, name="delete_building"),
    path("contribution/fix/refuse", refuse_contribution, name="refuse_contribution"),
    path(
        "contribution/fix/update_building",
        update_building,
        name="update_building",
    ),
    path("contribution/fix/merge_buildings", merge_buildings, name="merge_buildings"),
    path("__debug__/", include("debug_toolbar.urls")),
    path("webhook/", include("webhook.urls")),
    path("__test__/error/", test_error, name="test_error"),
]
