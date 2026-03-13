from datetime import date

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.exceptions import BadRequest
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.services.kpi import get_building_change_stats

MIN_SINCE_DATE = date(2024, 1, 1)


class BuildingChangeStatsView(RNBLoggingMixin, APIView):
    """
    GET /api/alpha/buildings/change_stats?since=YYYY-MM-DD&until=YYYY-MM-DD
    Retourne le nombre de modifications/créations de bâtiments par jour
    (import_bdtopo, import_bal, contributions).
    """

    @rnb_doc(
        {
            "get": {
                "summary": "Statistiques de modifications de bâtiments par jour",
                "description": (
                    "Retourne le nombre de modifications/créations de bâtiments par jour "
                    "(import_bdtopo, import_bal, contributions) entre deux dates. "
                    "Les paramètres since et until sont requis au format ISO YYYY-MM-DD."
                ),
                "operationId": "getBuildingChangeStats",
                "parameters": [
                    {
                        "name": "since",
                        "in": "query",
                        "description": "Date de début (inclusive), format YYYY-MM-DD. Ne peut pas être antérieure au 2024-01-01.",
                        "required": True,
                        "schema": {"type": "string", "format": "date"},
                        "example": "2024-01-01",
                    },
                    {
                        "name": "until",
                        "in": "query",
                        "description": "Date de fin (inclusive), format YYYY-MM-DD.",
                        "required": True,
                        "schema": {"type": "string", "format": "date"},
                        "example": "2024-01-31",
                    },
                ],
            }
        }
    )
    def get(self, request: Request) -> Response:
        since_str = request.query_params.get("since")
        until_str = request.query_params.get("until")

        if not since_str or not until_str:
            raise BadRequest(
                detail="Les paramètres since et until (YYYY-MM-DD) sont requis."
            )

        try:
            since = date.fromisoformat(since_str)
            until = date.fromisoformat(until_str)
        except ValueError:
            raise BadRequest(
                detail="since et until doivent être au format ISO YYYY-MM-DD."
            )

        if since > until:
            raise BadRequest(detail="since doit être antérieur ou égal à until.")

        if since < MIN_SINCE_DATE:
            raise BadRequest(
                detail=f"La date since ne peut pas être antérieure au {MIN_SINCE_DATE.isoformat()} (données non disponibles avant cette date)."
            )

        data = get_building_change_stats(since=since, until=until)
        return Response(data)
