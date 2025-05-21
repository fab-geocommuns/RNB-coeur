from rest_framework.permissions import BasePermission
from rest_framework_tracking.mixins import LoggingMixin


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


class RNBLoggingMixin(LoggingMixin):

    sensitive_fields = {"confirm_password"}

    def should_log(self, request, response):
        return request.query_params.get("from") != "monitoring"


class TokenScheme(OpenApiAuthenticationExtension):
    target_class = "rest_framework.authentication.TokenAuthentication"
    name = "RNBTokenAuth"
    priority = 1

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Toutes les requêtes liées aux ADS doivent faire l’objet d’une authentification. "
            "Pour vous identifier, utilisez le token fourni par l’équipe du RNB. "
            "Pour faire une demande de token, renseignez ce formulaire.\n\n"
            "Ajoutez une clé `Authorization` aux headers HTTP de chacune de vos requêtes. "
            "La valeur doit être votre token préfixé de la chaîne “Token”. "
            "Un espace sépare “Token” et votre token.\n\n"
            "Exemple:\n\n"
            "`Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b`",
        }
