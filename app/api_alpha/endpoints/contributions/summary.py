from api_alpha.exceptions import BadRequest
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.services.contribution_summary import (
    ALL_PERIOD,
    DEFAULT_WINDOW_DAYS,
    NEWCOMERS_LIMIT,
    RANKED_CITIES_LIMIT,
    TOP_LIMIT,
    WINDOWS_DAYS,
    get_all_contribution_rankings,
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
                    "days : les N derniers jours glissants, ou toutes les "
                    "contributions depuis toujours) : le nombre de "
                    "communes et d'organisations ayant contribué sur la période "
                    "(et celles dont c'est la toute première contribution), le "
                    "nombre de contributions de la période (contributions.total, "
                    f"imports exclus), les {TOP_LIMIT} "
                    "contributeurs, organisations et communes les plus actifs, et "
                    f"jusqu'à {NEWCOMERS_LIMIT} contributeurs ayant fait leur "
                    "toute première contribution sur la période, les derniers "
                    "arrivés d'abord. Les imports ne sont pas comptés comme des "
                    "contributions. Une contribution est une demande d'édition : "
                    "une fusion ou une scission compte une fois, quel que soit "
                    "le nombre de bâtiments concernés. Les données sont mises à jour environ "
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
                            + f" derniers jours, ou {ALL_PERIOD} pour toutes les "
                            "contributions depuis toujours (since vaut alors "
                            "null)."
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
                    + ", puis depuis toujours), "
                    "au même format que GET /api/alpha/contributions/summary/. "
                    "Les périodes sont toujours calculées au même instant "
                    "(même updated_at). Les données sont mises à jour environ "
                    "toutes les heures."
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


class ContributionRankingsView(RNBLoggingMixin, APIView):
    """
    GET /api/alpha/contributions/rankings/
    Long rankings of every period, for the details page of the summary.
    """

    @rnb_doc(
        {
            "get": {
                "summary": "Classements complets des contributions, toutes périodes",
                "description": (
                    "Retourne, pour chaque période ("
                    + ", ".join(f"{d} derniers jours" for d in WINDOWS_DAYS)
                    + ", puis depuis toujours) : tous les contributeurs et "
                    "toutes les organisations ayant contribué, et les "
                    f"{RANKED_CITIES_LIMIT} communes les plus éditées, les plus "
                    "actifs d'abord. Ce sont les versions longues de top dans "
                    "GET /api/alpha/contributions/summaries/, calculées au même "
                    "instant (même updated_at). Les données sont mises à jour "
                    "environ toutes les heures."
                ),
                "operationId": "getContributionRankings",
                "responses": {
                    "200": {
                        "description": (
                            "Les classements, de la période la plus courte à "
                            "la plus longue."
                        ),
                    }
                },
            }
        }
    )
    def get(self, request: Request) -> Response:
        return Response({"rankings": get_all_contribution_rankings()})
