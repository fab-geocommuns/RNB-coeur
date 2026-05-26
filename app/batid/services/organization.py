from batid.models import Organization, UserProfile
from batid.services.insee_siren import extract_org_name, fetch_siren_data
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q


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


def link_organization_to_users(org: Organization) -> None:
    """
    Attach users to the given organization based on:
    1. SIREN match — users whose Pro Connect SIRET starts with the org's SIREN (authoritative, overrides existing org)
    2. Email domain — users whose email domain matches the org's email_domain (fallback, only for users without an org)
    Staff and superusers are skipped unless the org is the RNB team.
    """
    simple_users_qs = User.objects.filter(is_staff=False, is_superuser=False)

    # RNB team — unconditionally assign all staff and superusers
    if org.name == settings.RNB_TEAM_ORG_NAME:
        for user in User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)):
            _set_user_org(user, org)

    # SIREN match — authoritative, always replayed
    if org.siren:
        for user in simple_users_qs.filter(pro_connect__siret__startswith=org.siren):
            _set_user_org(user, org)

    # Email domain — fallback, only for users without an org
    if org.email_domain:
        without_org = simple_users_qs.filter(
            email__endswith=f"@{org.email_domain}",
            profile__organization__isnull=True,
        )
        for user in without_org:
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
