from django.contrib import admin
from django.urls import path
from django.utils.html import format_html

from batid.models import Address
from batid.models import ADS
from batid.models import Contribution
from batid.models import Organization
from batid.models import DiffusionDatabase
from batid.views import export_ads
from batid.views import export_contributions
from batid.views import worker
from django.db.models.fields.json import JSONField
from jsoneditor.forms import JSONEditor


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "managed_cities")


admin.site.register(Organization, OrganizationAdmin)


class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "street_number",
        "street_rep",
        "street",
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
        "email",
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


class ADSAdmin(admin.ModelAdmin):
    list_filter = ["creator"]
    list_display = ("file_number", "created_at", "creator")


admin.site.register(ADS, ADSAdmin)


class DiffusionDatabaseAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "documentation_url",
        "publisher",
        "licence",
        "tags",
        "description",
        "image_url",
        "is_featured",
        "featured_summary",
        "attributes",
        "created_at",
        "updated_at",
    )
    formfield_overrides = {
        JSONField: {
            "widget": JSONEditor(
                init_options={"mode": "code", "modes": ["code", "text"]}
            )
        }
    }


admin.site.register(DiffusionDatabase, DiffusionDatabaseAdmin)


def get_admin_urls(urls):
    def get_urls():
        my_urls = [
            path(r"worker/", admin.site.admin_view(worker)),
            path(r"export_ads/", export_ads),
            path(r"export_contributions/", export_contributions),
        ]
        return my_urls + urls

    return get_urls


admin.site.get_urls = get_admin_urls(admin.site.get_urls())
