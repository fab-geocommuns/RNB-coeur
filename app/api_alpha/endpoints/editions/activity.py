from api_alpha.exceptions import BadRequest
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.services.edition_stats import (
    DEFAULT_LIMIT,
    MAX_DAYS,
    MAX_LIMIT,
    PERIOD_CURRENT_MONTH,
    PERIODS,
    get_edition_activity,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class EditionActivityView(RNBLoggingMixin, APIView):
    """
    GET /api/alpha/editions/activity/?period=current_month&limit=5
    GET /api/alpha/editions/activity/?days=30&limit=5
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
                    "La période est soit une fenêtre glissante des N derniers jours "
                    "(paramètre days), comparée aux N jours précédents, soit une période "
                    "calendaire (paramètre period, mois calendaires en heure de Paris). "
                    "Les imports de données ne sont pas comptés. Les données sont mises à jour toutes "
                    "les 10 minutes environ."
                ),
                "operationId": "getEditionActivity",
                "parameters": [
                    {
                        "name": "period",
                        "in": "query",
                        "description": (
                            "Période calendaire : current_month, last_month ou all. "
                            "Ne peut pas être combiné avec days."
                        ),
                        "required": False,
                        "schema": {
                            "type": "string",
                            "enum": PERIODS,
                            "default": PERIOD_CURRENT_MONTH,
                        },
                    },
                    {
                        "name": "days",
                        "in": "query",
                        "description": (
                            "Fenêtre glissante des N derniers jours, entre 1 et "
                            f"{MAX_DAYS}. La clé de la période vaut alors last_N_days."
                        ),
                        "required": False,
                        "schema": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_DAYS,
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
        days = None
        if "days" in request.query_params:
            if "period" in request.query_params:
                raise BadRequest(
                    detail="Les paramètres period et days ne peuvent pas être combinés."
                )
            try:
                days = int(request.query_params["days"])
            except ValueError:
                days = 0
            if not 1 <= days <= MAX_DAYS:
                raise BadRequest(
                    detail=f"Le paramètre days doit être un entier entre 1 et {MAX_DAYS}."
                )

        period = request.query_params.get("period", PERIOD_CURRENT_MONTH)
        if period not in PERIODS:
            raise BadRequest(
                detail=f"Le paramètre period doit valoir {', '.join(PERIODS)}."
            )

        try:
            limit = int(request.query_params.get("limit", DEFAULT_LIMIT))
        except ValueError:
            limit = 0
        if not 1 <= limit <= MAX_LIMIT:
            raise BadRequest(
                detail=f"Le paramètre limit doit être un entier entre 1 et {MAX_LIMIT}."
            )

        return Response(get_edition_activity(period, limit, days))
