from django.apps import AppConfig


class BatidConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "batid"

    def ready(self):
        from batid.signals import receivers  # noqa
        from api_alpha.utils import drf_spectacular_extension  # noqa
