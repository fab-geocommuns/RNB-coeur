from django_otp.admin import OTPAdminSite


class RNBAdminSite(OTPAdminSite):
    """Default admin site, requiring a verified second factor in every environment."""

    def __init__(self, name="admin"):
        # OTPAdminSite defaults to "otpadmin"; the "admin:" URL namespace is used across the code
        super().__init__(name=name)
