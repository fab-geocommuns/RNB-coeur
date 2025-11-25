from rest_framework.exceptions import NotFound
from rest_framework.views import APIView

from api_alpha.pagination import BuildingCursorPagination
from api_alpha.serializers.serializers import BuildingPlotSerializer
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.exceptions import PlotUnknown
from batid.services.bdg_on_plot import get_buildings_on_plot


class BuildingPlotView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Bâtiments sur une parcelle cadastrale",
                "description": "Cet endpoint permet d'obtenir une liste paginée des bâtiments présents sur une parcelle cadastrale. Les bâtiments sont triés par taux de recouvrement décroissant entre le bâtiment et la parcelle (le bâtiment entièrement sur une parcelle arrive avant celui à moitié sur la parcelle). La méthode de filtrage est purement géométrique et ne tient pas compte du lien fiscal entre le bâtiment et la parcelle. Des faux positifs sont donc possibles. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "plotBuildings",
                "parameters": [
                    {
                        "name": "plot_id",
                        "in": "path",
                        "description": "Identifiant de la parcelle cadastrale.",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "01402000AB0051",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée des bâtiments présents sur la parcelle cadastrale",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "next": {
                                            "type": "string",
                                            "description": "URL de la page de résultats suivante",
                                            "nullable": True,
                                        },
                                        "previous": {
                                            "type": "string",
                                            "description": "URL de la page de résultats précédente",
                                            "nullable": True,
                                        },
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "allOf": [
                                                    {
                                                        "$ref": "#/components/schemas/Building"
                                                    },
                                                    {
                                                        "type": "number",
                                                        "name": "bdg_cover_ratio",
                                                        "description": "Taux d'intersection entre le bâtiment et la parcelle. Ce taux est compris entre 0 et 1. Un taux de 1 signifie que la parcelle couvre entièrement le bâtiment.",
                                                        "example": 0.65,
                                                    },
                                                ]
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request, plot_id, *args, **kwargs):
        try:
            bdgs = get_buildings_on_plot(plot_id)
        except PlotUnknown:
            raise NotFound("Plot unknown")

        paginator = BuildingCursorPagination()
        paginated_bdgs = paginator.paginate_queryset(bdgs, request)
        serializer = BuildingPlotSerializer(paginated_bdgs, many=True)

        return paginator.get_paginated_response(serializer.data)
