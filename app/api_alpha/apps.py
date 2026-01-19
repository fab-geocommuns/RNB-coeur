import yaml
from django.apps import AppConfig


# Définition de la classe pour le block scalar "|"
class LiteralStr(str):
    """Force PyYAML to use block scalar '|' for multilines"""


def literal_str_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


class ApiAlphaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api_alpha"

    def ready(self):
        """Method called one at startup"""
        yaml.add_representer(LiteralStr, literal_str_representer)
