from django.contrib.admin.apps import AdminConfig


class RNBAdminConfig(AdminConfig):
    # The site class lives in app.admin: importing django_otp.admin here would load
    # models before the app registry is ready.
    default_site = "app.admin.RNBAdminSite"
