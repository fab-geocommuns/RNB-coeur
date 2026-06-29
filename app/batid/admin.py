from batid.models import (
    ADS,
    Address,
    BuildingImport,
    Contribution,
    DiffusionDatabase,
    Organization,
    UserProfile,
)
from batid.views import (
    export_ads,
    export_contributions,
    rollback_confirm_view,
    rollback_view,
    worker,
)
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.db.models.fields.json import JSONField
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from jsoneditor.forms import JSONEditor  # type: ignore[import-untyped]

# Fields the admin reconciles when merging two organizations.
MERGE_FIELDS = ("name", "short_name", "siren", "email_domain", "managed_cities")


def _parse_managed_cities(raw):
    """Parse the comma-separated managed_cities input into a list, or None if empty."""
    if not raw:
        return None
    cities = [c.strip() for c in raw.split(",") if c.strip()]
    return cities or None


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "siren", "email_domain", "get_user_count", "managed_cities")
    search_fields = ("name", "siren", "email_domain")
    change_form_template = "admin/batid/organization/change_form.html"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(user_count=Count("user_profiles"))

    @admin.display(description="Utilisateurs", ordering="user_count")
    def get_user_count(self, obj):
        return obj.user_count

    def get_urls(self):
        custom = [
            path(
                "<int:target_id>/merge/",
                self.admin_site.admin_view(self.merge_view),
                name="batid_organization_merge",
            ),
        ]
        return custom + super().get_urls()

    def merge_view(self, request, target_id):
        """Merge another organization into the one being viewed (the target survives).

        The target's user profiles are kept; the absorbed org's profiles are moved onto
        the target, the chosen field values are applied, and the absorbed org is deleted
        — atomically. A SIREN guard refuses the merge when both orgs carry different,
        non-empty SIRENs (two distinct legal entities).
        """
        if not self.has_change_permission(request):
            raise PermissionDenied

        target = get_object_or_404(Organization, pk=target_id)

        absorbed_id = request.POST.get("absorbed") or request.GET.get("absorbed")
        absorbed = None
        if absorbed_id:
            absorbed = (
                Organization.objects.exclude(pk=target.pk)
                .filter(pk=absorbed_id)
                .first()
            )

        # SIREN guard — on the original DB values, regardless of what the admin typed.
        siren_conflict = bool(
            absorbed
            and target.siren
            and absorbed.siren
            and target.siren != absorbed.siren
        )

        if (
            request.method == "POST"
            and absorbed
            and "confirm" in request.POST
            and not siren_conflict
        ):
            absorbed_name = absorbed.name
            with transaction.atomic():
                # Move profiles before deleting the absorbed org, otherwise
                # on_delete=SET_NULL would null them out.
                moved = UserProfile.objects.filter(organization=absorbed).update(
                    organization=target
                )
                # Delete the absorbed org before writing the chosen unique fields
                # (siren/email_domain), to avoid a unique-constraint conflict when the
                # retained value comes from the absorbed org.
                absorbed.delete()
                target.name = (request.POST.get("name") or "").strip() or target.name
                target.short_name = (
                    request.POST.get("short_name") or ""
                ).strip() or None
                target.siren = (request.POST.get("siren") or "").strip() or None
                target.email_domain = (
                    request.POST.get("email_domain") or ""
                ).strip() or None
                target.managed_cities = _parse_managed_cities(
                    request.POST.get("managed_cities")
                )
                target.save()  # replays link_organization_to_users
            messages.success(
                request,
                f"{moved} utilisateur(s) déplacé(s). Organisation "
                f"« {absorbed_name} » fusionnée puis supprimée.",
            )
            return redirect("admin:batid_organization_change", target.pk)

        if siren_conflict:
            messages.error(
                request,
                "Fusion refusée : les deux organisations portent des SIREN "
                "différents (entités légales distinctes).",
            )

        rows = []
        for field in MERGE_FIELDS:
            rows.append(
                {
                    "name": field,
                    "target": getattr(target, field),
                    "absorbed": getattr(absorbed, field) if absorbed else None,
                }
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"Fusionner une organisation dans « {target.name} »",
            "target": target,
            "absorbed": absorbed,
            "siren_conflict": siren_conflict,
            "rows": rows,
            "candidates": Organization.objects.exclude(pk=target.pk).order_by("name"),
        }
        return render(request, "admin/batid/organization/merge.html", context)


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
    list_display = (
        "rnb_id",
        "text",
        "created_at",
        "user",
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
    fields = (
        "organization",
        "job_title",
        "max_allowed_contributions",
        "total_contributions",
    )
    readonly_fields = ("total_contributions",)
    autocomplete_fields = ("organization",)


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
    list_display = [*BaseUserAdmin.list_display, "get_organization_name"]  # type: ignore[misc]

    @admin.display(description="Organisation", ordering="profile__organization__name")
    def get_organization_name(self, obj):

        if obj is None or obj.profile is None or obj.profile.organization is None:
            return "-"

        return obj.profile.organization.name


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
