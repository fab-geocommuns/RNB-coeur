from api_alpha.exceptions import BadRequest
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.services.contribution_summary import (
    DEFAULT_WINDOW_DAYS,
    NEWCOMERS_LIMIT,
    TOP_LIMIT,
    WINDOWS_DAYS,
    get_contribution_summary,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class ContributionSummaryView(RNBLoggingMixin, APIView):
    """
    GET /api/alpha/contributions/summary/
    Synthèse publique des contributions de la communauté, affichée sur la page
    d'accueil du site.
    """

    @rnb_doc(
        {
            "get": {
                "summary": "Synthèse des contributions de la communauté",
                "description": (
                    "Retourne en une seule réponse, pour une fenêtre glissante des "
                    "N derniers jours (paramètre days) : le nombre de communes et "
                    "d'organisations ayant déjà contribué (et "
                    "celles qui l'ont fait pour la première fois dans la fenêtre), "
                    "les modifications de bâtiments des N derniers jours complets "
                    f"(toutes sources, dont les contributions), les {TOP_LIMIT} "
                    "contributeurs, organisations et communes les plus actifs, et "
                    f"jusqu'à {NEWCOMERS_LIMIT} contributeurs ayant fait leur "
                    "toute première contribution "
                    "dans la fenêtre. Les imports ne sont pas comptés comme des "
                    "contributions. Les données sont mises à jour environ "
                    "toutes les heures."
                ),
                "operationId": "getContributionSummary",
                "parameters": [
                    {
                        "name": "days",
                        "in": "query",
                        "description": (
                            "Longueur de la fenêtre glissante, en jours : "
                            + " ou ".join(str(d) for d in WINDOWS_DAYS)
                            + "."
                        ),
                        "required": False,
                        "schema": {
                            "type": "integer",
                            "enum": WINDOWS_DAYS,
                            "default": DEFAULT_WINDOW_DAYS,
                        },
                    }
                ],
            }
        }
    )
    def get(self, request: Request) -> Response:
        days_param = request.query_params.get("days", str(DEFAULT_WINDOW_DAYS))
        if days_param not in [str(d) for d in WINDOWS_DAYS]:
            raise BadRequest(
                detail="Le paramètre days doit valoir "
                + " ou ".join(str(d) for d in WINDOWS_DAYS)
                + "."
            )
        return Response(get_contribution_summary(int(days_param)))
