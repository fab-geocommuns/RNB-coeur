from api_alpha.exceptions import BadRequest
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.services.edition_stats import (
    DEFAULT_DAYS,
    DEFAULT_LIMIT,
    MAX_DAYS,
    MAX_LIMIT,
    PERIOD_ALL,
    get_edition_activity,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class EditionActivityView(RNBLoggingMixin, APIView):
    """
    GET /api/alpha/editions/activity/?days=30&limit=5
    GET /api/alpha/editions/activity/?period=all&limit=5
    Statistiques publiques des éditions de la communauté sur une période.
    """

    @rnb_doc(
        {
            "get": {
                "summary": "Activité d'édition de la communauté",
                "description": (
                    "Retourne, pour une période, le nombre de contributions faites par "
                    "les contributeurs (une contribution peut modifier plusieurs "
                    "bâtiments ou plusieurs attributs, ex. une fusion), le nombre de "
                    "communes concernées et de contributeurs, les classements des "
                    "contributeurs, organisations, communes et départements, ainsi que "
                    "ceux ayant fait leur toute première contribution sur la période. "
                    "La période est une fenêtre glissante des N derniers jours "
                    "(paramètre days, 30 par défaut), comparée aux N jours précédents, "
                    "ou tout l'historique (period=all). "
                    "Les imports de données ne sont pas comptés. Les données sont mises à jour toutes "
                    "les 10 minutes environ."
                ),
                "operationId": "getEditionActivity",
                "parameters": [
                    {
                        "name": "period",
                        "in": "query",
                        "description": (
                            "all pour tout l'historique, au lieu d'une fenêtre "
                            "glissante. Ne peut pas être combiné avec days."
                        ),
                        "required": False,
                        "schema": {"type": "string", "enum": [PERIOD_ALL]},
                    },
                    {
                        "name": "days",
                        "in": "query",
                        "description": (
                            "Fenêtre glissante des N derniers jours, entre 1 et "
                            f"{MAX_DAYS}. La clé de la période vaut last_N_days."
                        ),
                        "required": False,
                        "schema": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_DAYS,
                            "default": DEFAULT_DAYS,
                        },
                        "example": 30,
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "description": f"Taille des classements, entre 1 et {MAX_LIMIT}.",
                        "required": False,
                        "schema": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_LIMIT,
                            "default": DEFAULT_LIMIT,
                        },
                    },
                ],
            }
        }
    )
    def get(self, request: Request) -> Response:
        params = request.query_params
        if "period" in params:
            if "days" in params:
                raise BadRequest(
                    detail="Les paramètres period et days ne peuvent pas être combinés."
                )
            if params["period"] != PERIOD_ALL:
                raise BadRequest(
                    detail=f"Le paramètre period doit valoir {PERIOD_ALL}."
                )
            days = None
        else:
            try:
                days = int(params.get("days", DEFAULT_DAYS))
            except ValueError:
                days = 0
            if not 1 <= days <= MAX_DAYS:
                raise BadRequest(
                    detail=f"Le paramètre days doit être un entier entre 1 et {MAX_DAYS}."
                )

        try:
            limit = int(params.get("limit", DEFAULT_LIMIT))
        except ValueError:
            limit = 0
        if not 1 <= limit <= MAX_LIMIT:
            raise BadRequest(
                detail=f"Le paramètre limit doit être un entier entre 1 et {MAX_LIMIT}."
            )

        return Response(get_edition_activity(days, limit))
