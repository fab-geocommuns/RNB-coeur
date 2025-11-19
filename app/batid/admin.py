from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models.fields.json import JSONField
from django.urls import path
from django.utils.html import format_html
from jsoneditor.forms import JSONEditor  # type: ignore[import-untyped]

from batid.models import Address
from batid.models import ADS
from batid.models import BuildingImport
from batid.models import Contribution
from batid.models import DiffusionDatabase
from batid.models import Organization
from batid.models import UserProfile
from batid.views import export_ads
from batid.views import export_contributions
from batid.views import worker


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "managed_cities")


admin.site.register(Organization, OrganizationAdmin)


class BuildingImportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "import_source",
        "departement",
        "created_at",
        "updated_at",
        "candidate_created_count",
        "building_created_count",
        "building_updated_count",
        "building_refused_count",
        "bulk_launch_uuid",
    )


admin.site.register(BuildingImport, BuildingImportAdmin)


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


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profile"
    fields = ("job_title", "max_allowed_contributions", "total_contributions")
    readonly_fields = ("total_contributions",)


class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "job_title",
        "max_allowed_contributions",
        "total_contributions",
    )
    list_filter = ("job_title",)
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    readonly_fields = ("total_contributions",)


admin.site.register(UserProfile, UserProfileAdmin)


class CustomUserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)


# Unregister the default User admin and register the custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


def get_admin_urls(urls):
    def get_urls():
        my_urls = [
            path(r"worker/", admin.site.admin_view(worker)),
            path(r"export_ads/", export_ads),
            path(r"export_contributions/", export_contributions),
        ]
        return my_urls + urls

    return get_urls


admin.site.get_urls = get_admin_urls(admin.site.get_urls())  # type: ignore[method-assign]


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")


BaseUserAdmin.add_form = CustomUserCreationForm
BaseUserAdmin.add_fieldsets = (
    (
        None,
        {
            "classes": ("wide",),
            "fields": ("username", "email", "password1", "password2"),
        },
    ),
)
