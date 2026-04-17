from django.conf import settings
from django.contrib.auth.models import User

from batid.models import Organization
from batid.services.insee_siren import extract_org_name
from batid.services.insee_siren import fetch_siren_data


def link_user_to_organization(user: User) -> None:
    # Staff and superusers always belong to the RNB team — skip all other logic
    if user.is_staff or user.is_superuser:
        org = Organization.objects.filter(name=settings.RNB_TEAM_ORG_NAME).first()
        if org:
            user.profile.organization = org
            user.profile.save(update_fields=["organization"])
        return

    # SIREN match — authoritative, always replayed, always updates profile.organization
    if hasattr(user, "pro_connect") and len(user.pro_connect.siret) >= 9:
        siren = user.pro_connect.siret[:9]
        org = Organization.objects.filter(siren=siren).first()
        if org is None:
            org = _create_org_from_siren(siren)
        if org:
            user.profile.organization = org
            user.profile.save(update_fields=["organization"])
            return

    # Email domain — fallback, only when profile has no org yet
    if user.profile.organization is None and user.email and "@" in user.email:
        domain = user.email.split("@")[1]
        org = Organization.objects.filter(email_domain=domain).first()
        if org:
            user.profile.organization = org
            user.profile.save(update_fields=["organization"])


def _create_org_from_siren(siren: str) -> Organization | None:
    data = fetch_siren_data(siren)
    if not data:
        return None
    name = extract_org_name(data.get("uniteLegale", {}))
    if not name:
        return None
    org, _ = Organization.objects.get_or_create(siren=siren, defaults={"name": name})
    return org
