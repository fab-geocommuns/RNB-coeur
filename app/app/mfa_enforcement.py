from enum import StrEnum


class MFAEnforcement(StrEnum):
    """Second factor policy for the password login (/login/). The admin always requires it."""

    # the code is never asked, even for users who configured an app
    OFF = "OFF"
    # asked to users with an app; staff, superusers and the "MFA required" group must
    # enroll, others are offered enrollment
    OPTIONAL = "OPTIONAL"
    # every user must have an app to log in
    REQUIRED = "REQUIRED"
