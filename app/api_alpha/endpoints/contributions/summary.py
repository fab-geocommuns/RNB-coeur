from api_alpha.exceptions import BadRequest
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.services.contribution_summary import (
    ALL_PERIOD,
    DEFAULT_WINDOW_DAYS,
    EDITION_OPENING,
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
                    "Retourne en une seule réponse, pour une période (paramètre "
                    "days : les N derniers jours glissants, ou depuis "
                    "l'ouverture de l'édition collaborative) : le nombre de "
                    "communes et d'organisations ayant contribué sur la période "
                    "(et celles dont c'est la toute première contribution), les "
                    "modifications de bâtiments des jours complets de la période "
                    f"(toutes sources, dont les contributions), les {TOP_LIMIT} "
                    "contributeurs, organisations et communes les plus actifs, et "
                    f"jusqu'à {NEWCOMERS_LIMIT} contributeurs ayant fait leur "
                    "toute première contribution sur la période, les derniers "
                    "arrivés d'abord. Les imports ne sont pas comptés comme des "
                    "contributions. Les données sont mises à jour environ "
                    "toutes les heures."
                ),
                "operationId": "getContributionSummary",
                "parameters": [
                    {
                        "name": "days",
                        "in": "query",
                        "description": (
                            "Période : les "
                            + " ou ".join(str(d) for d in WINDOWS_DAYS)
                            + f" derniers jours, ou {ALL_PERIOD} depuis "
                            "l'ouverture de l'édition collaborative ("
                            + EDITION_OPENING.date().isoformat()
                            + ")."
                        ),
                        "required": False,
                        "schema": {
                            "type": "string",
                            "enum": [str(d) for d in WINDOWS_DAYS] + [ALL_PERIOD],
                            "default": str(DEFAULT_WINDOW_DAYS),
                        },
                    }
                ],
            }
        }
    )
    def get(self, request: Request) -> Response:
        days_param = request.query_params.get("days", str(DEFAULT_WINDOW_DAYS))
        if days_param == ALL_PERIOD:
            return Response(get_contribution_summary(None))
        if days_param not in [str(d) for d in WINDOWS_DAYS]:
            raise BadRequest(
                detail="Le paramètre days doit valoir "
                + ", ".join(str(d) for d in WINDOWS_DAYS)
                + f" ou {ALL_PERIOD}."
            )
        return Response(get_contribution_summary(int(days_param)))
