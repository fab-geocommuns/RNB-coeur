from django.urls import path
from django.contrib import admin
from batid.views import worker

from batid.models import Organization


class OrganozationAdmin(admin.ModelAdmin):
    list_display = ("name", "managed_cities")


# Display and edit models in admin
admin.site.register(Organization, OrganozationAdmin)


def get_admin_urls(urls):
    def get_urls():
        my_urls = [path(r"worker/", admin.site.admin_view(worker))]
        return my_urls + urls

    return get_urls


admin.site.get_urls = get_admin_urls(admin.site.get_urls())
