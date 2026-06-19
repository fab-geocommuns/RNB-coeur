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


def _is_siren_anchored(user: User) -> bool:
    """True if the user's current organization carries exactly the SIREN of their
    ProConnect SIRET — i.e. they are correctly placed by the authoritative signal and
    must not be reassigned by a weaker email-domain match."""
    if not (hasattr(user, "pro_connect") and len(user.pro_connect.siret) >= 9):
        return False
    current_org = getattr(getattr(user, "profile", None), "organization", None)
    return current_org is not None and current_org.siren == user.pro_connect.siret[:9]


def link_user_to_organization(user: User) -> None:
    """
    Link a user to an organization based on the following logic:
    1. Staff and superusers always belong to the RNB team
    2. SIRET from Pro Connect — users log in via Pro Connect, we have their SIRET, we can extract the SIREN and find the org
    3. Email domain — organization have an email domain, if the user's email matches that domain, we link them to the org.
    """

    org = None

    # Staff and superusers always belong to the RNB team — skip all other logic
    if user.is_staff or user.is_superuser:
        org = Organization.objects.filter(name=settings.RNB_TEAM_ORG_NAME).first()
        if org:
            _set_user_org(user, org)
        return

    # -----------

    # First, we get the user's email domain and prepare a filter for organizations.
    user_email_domain = (
        user.email.split("@")[1] if user.email and "@" in user.email else None
    )
    org_filter = Q(email_domain=user_email_domain)

    # Then, we get the user's SIRET from Pro Connect, if available, and extract the SIREN.
    user_siren = None
    if hasattr(user, "pro_connect") and len(user.pro_connect.siret) >= 9:
        user_siren = user.pro_connect.siret[:9]
        org_filter |= Q(siren=user_siren)

    # We use the org_filter to get candidate organizations from the database. This is a single query that returns at most 2 organizations (one by SIREN, one by email domain).
    matching_organizations = Organization.objects.filter(org_filter)

    if len(matching_organizations) == 0 and user_siren:

        org = _create_org_from_siren(user_siren)

    elif len(matching_organizations) == 1:

        # A single candidate matched either by SIREN or by email domain.
        org = matching_organizations[0]

        # We check if we can update empty `siren` or empty `email_domain` on the org, using user info
        org_has_changed = False
        if not org.siren and user_siren:
            org.siren = user_siren
            org_has_changed = True

        if not org.email_domain:
            org.email_domain = user_email_domain
            org_has_changed = True

        if org_has_changed:
            org.save()

    elif len(matching_organizations) == 2:

        # Two distinct candidates (one by siren, one by domain): prefer the one
        # carrying the same siren. No enrichment — reconcile via the admin merge tool.
        org = next(o for o in matching_organizations if o.siren == user_siren)

    # Finally, if we found an org to link to the user, we proceed
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

    # Email domain — reassigns any matching user, except one already anchored by SIREN
    # (their current org carries their ProConnect SIREN): SIREN placement is authoritative
    # and must not be overridden by a weaker email-domain signal.
    if org.email_domain:
        for user in simple_users_qs.filter(email__endswith=f"@{org.email_domain}"):
            if not _is_siren_anchored(user):
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
