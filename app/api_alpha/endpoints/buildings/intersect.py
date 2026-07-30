from api_alpha.pagination import BuildingCursorPagination
from api_alpha.serializers.serializers import (
    BuildingIntersectQuerySerializer,
    BuildingIntersectSerializer,
)
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.services.bdg_intersect import get_buildings_intersecting_polygon
from rest_framework.views import APIView


class BuildingIntersectView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Bâtiments intersectant un polygone",
                "description": "Cet endpoint permet d'obtenir une liste paginée des bâtiments dont la géométrie intersecte le polygone fourni. Les bâtiments sont triés par IoU (Intersection over Union) décroissant entre leur géométrie et le polygone fourni. Les bâtiments dont la géométrie RNB est un point sont inclus si ce point est dans le polygone; ils sont placés en fin de liste. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "intersectBuildings",
                "parameters": [
                    {
                        "name": "shape",
                        "in": "query",
                        "description": "Polygone au format WKT (WGS84). Seul le type Polygon est accepté (pas de MultiPolygon), la géométrie doit être en 2D (les géométries 3D, avec une coordonnée Z, sont refusées) et son aire doit être inférieure à 1 km².",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "POLYGON((5.7213 45.1848, 5.7213 45.1854, 5.7222 45.1854, 5.7222 45.1848, 5.7213 45.1848))",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée des bâtiments intersectant le polygone, triée par IoU décroissant",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "next": {
                                            "type": ["string", "null"],
                                            "description": "URL de la page de résultats suivante",
                                        },
                                        "previous": {
                                            "type": ["string", "null"],
                                            "description": "URL de la page de résultats précédente",
                                        },
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "allOf": [
                                                    {
                                                        "$ref": "#/components/schemas/Building"
                                                    },
                                                    {
                                                        "type": "object",
                                                        "properties": {
                                                            "iou": {
                                                                "type": [
                                                                    "number",
                                                                    "null",
                                                                ],
                                                                "description": "Intersection over Union entre la géométrie du bâtiment RNB et le polygone fourni : aire de l'intersection divisée par l'aire de l'union, entre 0 et 1. Vaut `null` lorsque la géométrie du bâtiment RNB est un point.",
                                                                "example": 0.82,
                                                            },
                                                            "input_covered_by_rnb": {
                                                                "type": [
                                                                    "number",
                                                                    "null",
                                                                ],
                                                                "description": "Pourcentage du polygone fourni qui est couvert par la géométrie du bâtiment RNB, entre 0 et 1. Vaut `null` lorsque la géométrie du bâtiment RNB est un point.",
                                                                "example": 0.9,
                                                            },
                                                            "rnb_covered_by_input": {
                                                                "type": [
                                                                    "number",
                                                                    "null",
                                                                ],
                                                                "description": "Pourcentage de la géométrie du bâtiment RNB qui est couvert par le polygone fourni, entre 0 et 1. Vaut `null` lorsque la géométrie du bâtiment RNB est un point.",
                                                                "example": 0.88,
                                                            },
                                                        },
                                                    },
                                                ]
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "400": {
                        "description": "Requête invalide : paramètre shape manquant, WKT non analysable, géométrie qui n'est pas un Polygon, géométrie 3D, polygone invalide ou aire supérieure à 1 km²",
                    },
                },
            }
        }
    )
    def get(self, request, *args, **kwargs):
        query_serializer = BuildingIntersectQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        poly = query_serializer.validated_data["shape"]

        bdgs = get_buildings_intersecting_polygon(poly)

        paginator = BuildingCursorPagination()
        paginated_bdgs = paginator.paginate_queryset(bdgs, request)
        serializer = BuildingIntersectSerializer(paginated_bdgs, many=True)

        return paginator.get_paginated_response(serializer.data)
