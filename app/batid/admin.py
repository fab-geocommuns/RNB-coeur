from batid.models import (
    ADS,
    Address,
    BuildingImport,
    Contribution,
    DiffusionDatabase,
    Organization,
    UserProfile,
)
from django.db.models import Count
from batid.views import (
    export_ads,
    export_contributions,
    rollback_confirm_view,
    rollback_view,
    worker,
)
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models.fields.json import JSONField
from django.urls import path
from jsoneditor.forms import JSONEditor  # type: ignore[import-untyped]


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "siren", "email_domain", "get_user_count", "managed_cities")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(user_count=Count("user_profiles"))

    @admin.display(description="Utilisateurs", ordering="user_count")
    def get_user_count(self, obj):
        return obj.user_count


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
        "review_user",
        "review_comment",
    )


admin.site.register(Contribution, ContributionAdmin)


class ADSAdmin(admin.ModelAdmin):
    list_filter = ["creator"]
    list_display = ("file_number", "created_at", "creator")


admin.site.register(ADS, ADSAdmin)


class DiffusionDatabaseAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "display_order",
        "documentation_url",
        "publisher",
        "licence",
        "tags",
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
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    readonly_fields = ("total_contributions",)


admin.site.register(UserProfile, UserProfileAdmin)


class CustomUserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = BaseUserAdmin.list_display + ("get_organization_name",)

    @admin.display(description="Organisation", ordering="profile__organization__name")
    def get_organization_name(self, obj):
        try:
            return obj.profile.organization.name
        except AttributeError:
            return "-"


# Unregister the default User admin and register the custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


def get_admin_urls(urls):
    def get_urls():
        my_urls = [
            path(r"worker/", admin.site.admin_view(worker)),
            path(r"export_ads/", export_ads),
            path(r"export_contributions/", export_contributions),
            path(
                r"rollback/",
                admin.site.admin_view(rollback_view),
                name="rollback",
            ),
            path(
                r"rollback/confirm/",
                admin.site.admin_view(rollback_confirm_view),
                name="rollback_confirm",
            ),
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
