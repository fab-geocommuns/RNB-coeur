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
    get_all_contribution_summaries,
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
                    "toutes les heures. Pour afficher plusieurs périodes "
                    "côte à côte, utilisez plutôt "
                    "GET /api/alpha/contributions/summaries/ : des appels "
                    "séparés pendant une mise à jour peuvent renvoyer des "
                    "périodes calculées à des moments différents."
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


class ContributionSummariesView(RNBLoggingMixin, APIView):
    """
    GET /api/alpha/contributions/summaries/
    Every period of the contribution summary in one response, all computed at
    the same instant, so that they can be shown side by side.
    """

    @rnb_doc(
        {
            "get": {
                "summary": "Synthèses des contributions, toutes périodes",
                "description": (
                    "Retourne en une seule réponse la synthèse de chaque "
                    "période ("
                    + ", ".join(f"{d} derniers jours" for d in WINDOWS_DAYS)
                    + ", puis depuis l'ouverture de l'édition collaborative), "
                    "au même format que GET /api/alpha/contributions/summary/. "
                    "Les périodes sont toujours calculées au même instant "
                    "(même updated_at) : une période courte ne compte jamais "
                    "plus de communes ou d'organisations qu'une période plus "
                    "longue. Les données sont mises à jour environ toutes les "
                    "heures."
                ),
                "operationId": "getContributionSummaries",
                "responses": {
                    "200": {
                        "description": (
                            "Les synthèses, de la période la plus courte à la "
                            "plus longue."
                        ),
                    }
                },
            }
        }
    )
    def get(self, request: Request) -> Response:
        return Response({"summaries": get_all_contribution_summaries()})
