from django.contrib import admin
from django.urls import path
from django.utils.html import format_html

from batid.models import Address
from batid.models import Contribution
from batid.models import Organization
from batid.views import worker


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "managed_cities")


admin.site.register(Organization, OrganizationAdmin)


class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "street_number",
        "street_rep",
        "street_type",
        "street_name",
        "city_name",
        "city_zipcode",
        "city_insee_code",
        "created_at",
    )


admin.site.register(Address, AddressAdmin)


class ContributionAdmin(admin.ModelAdmin):
    list_filter = ["status"]
    list_display = (
        "rnb_id",
        "text",
        "created_at",
        "status",
        "fix_issue",
        "review_user",
        "review_comment",
    )

    def fix_issue(self, obj):
        if obj.status == "pending":
            link = f"/contribution/fix/{obj.id}"
            return format_html('<a href="{}">{}</a>', link, "résoudre")


admin.site.register(Contribution, ContributionAdmin)


def get_admin_urls(urls):
    def get_urls():
        my_urls = [path(r"worker/", admin.site.admin_view(worker))]
        return my_urls + urls

    return get_urls


admin.site.get_urls = get_admin_urls(admin.site.get_urls())
