from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.services.contribution_summary import (
    NEW_CITIES_LIMIT,
    TOP_LIMIT,
    WINDOW_DAYS,
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
                    "Retourne en une seule réponse : le nombre de communes et "
                    "d'organisations ayant déjà contribué (et celles qui l'ont fait "
                    f"pour la première fois ces {WINDOW_DAYS} derniers jours), le "
                    f"nombre de modifications de bâtiments des {WINDOW_DAYS} derniers "
                    "jours complets (toutes sources, dont les contributions), les "
                    f"{TOP_LIMIT} contributeurs, organisations et communes les plus "
                    f"actifs sur {WINDOW_DAYS} jours glissants et jusqu'à "
                    f"{NEW_CITIES_LIMIT} communes améliorées pour la première fois. "
                    "Les imports de données et les contributions de l'équipe RNB ne "
                    "sont pas comptés, sauf dans les modifications de bâtiments. "
                    "Les cumuls sont mis à jour chaque nuit, le reste environ "
                    "toutes les heures."
                ),
                "operationId": "getContributionSummary",
            }
        }
    )
    def get(self, request: Request) -> Response:
        return Response(get_contribution_summary())
