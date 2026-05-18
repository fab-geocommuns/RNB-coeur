from batid.models import Organization, UserProfile
from batid.services.insee_siren import extract_org_name, fetch_siren_data
from django.conf import settings
from django.contrib.auth.models import User


def _set_user_org(user: User, org: Organization) -> None:
    """Assign an organization to the user's profile (creating the profile if needed)."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.organization = org
    profile.save(update_fields=["organization"])


def link_user_to_organization(user: User) -> None:
    """
    Link a user to an organization based on the following logic:
    1. Staff and superusers always belong to the RNB team
    2. SIRET from Pro Connect — users log in via Pro Connect, we have their SIRET, we can extract the SIREN and find the org
    3. Email domain — organization have an email domain, if the user's email matches that domain, we link them to the org.
    """

    # Staff and superusers always belong to the RNB team — skip all other logic
    if user.is_staff or user.is_superuser:
        org = Organization.objects.filter(name=settings.RNB_TEAM_ORG_NAME).first()
        if org:
            _set_user_org(user, org)
        return

    # SIREN match — authoritative, always replayed
    if hasattr(user, "pro_connect") and len(user.pro_connect.siret) >= 9:

        # SIREN number is the first 9 digits of the SIRET
        siren = user.pro_connect.siret[:9]
        org = Organization.objects.filter(siren=siren).first()
        if org is None:
            org = _create_org_from_siren(siren)
        if org:
            _set_user_org(user, org)
            return

    # Email domain — fallback, only when user has no org yet
    if user.email and "@" in user.email:
        has_org = UserProfile.objects.filter(
            user=user, organization__isnull=False
        ).exists()
        if not has_org:
            domain = user.email.split("@")[1]
            org = Organization.objects.filter(email_domain=domain).first()
            if org:
                _set_user_org(user, org)


def _create_org_from_siren(siren: str) -> Organization | None:
    data = fetch_siren_data(siren)
    if not data:
        return None
    name = extract_org_name(data.get("uniteLegale", {}))
    if not name:
        return None
    org, _ = Organization.objects.get_or_create(siren=siren, defaults={"name": name})
    return org
