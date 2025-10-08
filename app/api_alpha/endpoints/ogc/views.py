from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.pagination import OGCApiPagination
from api_alpha.serializers.serializers import BuildingGeoJSONSerializer
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import build_schema_ogc_endpoints
from api_alpha.utils.rnb_doc import rnb_doc
from batid.list_bdg import list_bdgs
from batid.services.rnb_id import clean_rnb_id


class OpenAPIRenderer(JSONRenderer):
    media_type = "application/vnd.oai.openapi+json;version=3.0"


class GeoJSONRenderer(JSONRenderer):
    media_type = "application/geo+json"


class OGCAPIBaseView(RNBLoggingMixin, APIView):
    def _get_conformance_link(self, request: Request, is_currrent_page=False):

        url = request.build_absolute_uri(reverse("ogc_conformance"))

        return {
            "href": url,
            "rel": "self" if is_currrent_page else "conformance",
            "type": "application/json",
            "title": "Les spécifications respectées par cette API",
        }

    def _get_collections_link(self, request: Request, is_currrent_page=False):

        url = request.build_absolute_uri(reverse("ogc_collections"))

        return {
            "href": url,
            "rel": "self" if is_currrent_page else "data",
            "type": "application/json",
            "title": "Liste des types de données disponibles dans cette API",
        }

    def _get_buildings_collection_link(self, request: Request, is_currrent_page=False):

        url = request.build_absolute_uri(reverse("ogc_buildings_collection"))
        return {
            "href": url,
            "rel": (
                "self" if is_currrent_page else "collection"
            ),  # Using 'collection' is more specific than 'data'
            "type": "application/json",
            "title": "Meta-données à propos de la liste des bâtiments disponibles dans le RNB",
        }

    def _get_buildings_items_link(self, request: Request, is_currrent_page=False):

        url = request.build_absolute_uri(reverse("ogc_buildings_items"))
        return {
            "href": url,
            "rel": "self" if is_currrent_page else "items",
            "type": "application/geo+json",
            "title": "Bâtiments disponibles dans le RNB",
        }

    def _get_buildings_collection(self, request: Request, is_currrent_page=False):
        # MODIFIED: Pass request down to the link helpers
        return {
            "id": "buildings",
            "title": "Bâtiments du RNB",
            "description": "Liste des bâtiments disponibles dans le RNB",
            "itemType": "feature",
            "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
            "extent": {
                "spatial": {
                    "bbox": [[-180.0, -90.0, 180.0, 90.0]],
                    "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                }
            },
            "links": [
                self._get_buildings_collection_link(request, is_currrent_page=True),
                self._get_buildings_items_link(request),
            ],
        }

    def _get_root_link(self, request: Request):

        url = request.build_absolute_uri(reverse("ogc_root"))
        return {
            "href": url,
            "rel": "root",
            "type": "application/json",
            "title": "Racine de l'API du RNB",
        }

    def _get_api_definition_link(self, request: Request):

        url = request.build_absolute_uri(reverse("ogc_openapi"))
        return {
            "href": url,
            "rel": "service-desc",
            "type": "application/vnd.oai.openapi+json;version=3.0",
            "title": "Définition OpenAPI de l'API OGC du RNB",
        }


class OGCIndexView(OGCAPIBaseView):
    @rnb_doc(
        {
            "get": {
                "summary": "Racine de l'API du RNB au standard OGC",
                "description": "Ce endpoint est le point d'entrée pour exploiter les données RNB au standard OGC.",
                "responses": {
                    "200": {
                        "description": "Principaux liens disponibles dans l'API",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "description": {"type": "string"},
                                        "links": {"type": "array"},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        schemes=["ogc"],
    )
    def get(self, request: Request, *args, **kwargs):

        data = {
            "title": "Bâtiments du RNB",
            "description": "Cette API fournit les bâtiments du RNB au format OGC API Features. ",
            "links": [
                self._get_root_link(request),
                self._get_conformance_link(request),
                self._get_collections_link(request),
                self._get_api_definition_link(request),
            ],
        }
        return Response(data)


class OGCConformanceView(OGCAPIBaseView):
    @rnb_doc(
        {
            "get": {
                "summary": "Déclaration de conformité de l'API du RNB au standard OGC",
                "description": "Liste les classes de conformité OGC auxquelles cette API adhère.",
                "responses": {
                    "200": {
                        "description": "Classes de conformité",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "conformsTo": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        }
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        schemes=["ogc"],
    )
    def get(self, request, *args, **kwargs):
        data = {
            "conformsTo": [
                "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
                "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
            ]
        }
        return Response(data)


class OGCCollectionsView(OGCAPIBaseView):
    @rnb_doc(
        {
            "get": {
                "summary": "Liste des collections de données",
                "description": "Ce endpoint liste les collections de données disponibles au standard OGC. Pour le moment, seuls les bâtiments sont disponibles.",
                "responses": {
                    "200": {
                        "description": "Liste des collections",
                    }
                },
            }
        },
        schemes=["ogc"],
    )
    def get(self, request: Request, *args, **kwargs):

        data = {
            "links": [
                self._get_collections_link(request, is_currrent_page=True),
                self._get_conformance_link(request),
                self._get_root_link(
                    request
                ),  # Changed to a proper self-referencing root link
            ],
            "collections": [
                self._get_buildings_collection(request),
            ],
        }
        return Response(data)


class OGCBuildingsCollectionView(OGCAPIBaseView):
    @rnb_doc(
        {
            "get": {
                "summary": "Métadonnées de la collection de bâtiments",
                "description": "Fournit des informations détaillées sur la collection de bâtiments.",

                "responses": {
                    "200": {
                        "description": "Métadonnées de la collection",
                    }
                },
            }
        },
        schemes=["ogc"],
    )
    def get(self, request: Request, *args, **kwargs):
        # MODIFIED: Pass request to the helper
        data = self._get_buildings_collection(request, is_currrent_page=True)
        return Response(data)


class OGCBuildingItemsView(OGCAPIBaseView):

    renderer_classes = [GeoJSONRenderer, JSONRenderer]

    @rnb_doc(
        {
            "get": {
                "summary": "Liste des bâtiments",
                "description": "Récupère une liste de bâtiments sous forme de FeatureCollection GeoJSON.",

                "parameters": [
                    {
                        "name": "bbox",
                        "in": "query",
                        "description": "Filtre géographique par Bounding Box.",
                        "schema": {"type": "array"},
                        "style": "form",
                    },
                    {
                        "name": "insee_code",
                        "in": "query",
                        "description": "Filtre les bâtiments dont la géométrie est située dans les limites géographiques de la commune ayant ce code INSEE.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "75101",
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "description": "Nombre maximum de bâtiments à retourner dans la page de résultats.",
                        "required": False,
                        "style": "form",
                        "schema": {
                            "type": "integer",
                            "default": 20,
                            "maximum": 100,
                            "minimum": 1,
                        },
                        "example": 50,
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Une FeatureCollection (GeoJSON) de bâtiments. Les résultats sont paginés.",
                        "content": {
                            "application/geo+json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "example": "FeatureCollection",
                                        },
                                        "features": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/BuildingGeoJSON"
                                            },
                                        },
                                        "numberReturned": {
                                            "type": "integer",
                                            "description": "Nombre de bâtiments retournés dans cette page de résultats.",
                                            "example": 20,
                                        },
                                        "timeStamp": {
                                            "type": "string",
                                            "format": "date-time",
                                            "description": "Horodatage de la génération de la réponse.",
                                            "example": "2025-12-25T13:37:00Z",
                                        },
                                        "links": {
                                            "type": "array",
                                            "description": "Liens de pagination et autres liens associés.",
                                            "items": {"type": "object"},
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        schemes=["ogc"],
    )
    def get(self, request: Request) -> Response:
        query_params = request.query_params.dict()

        with_plots_param = request.query_params.get("withPlots", None)
        with_plots = True if with_plots_param == "1" else False
        query_params["with_plots"] = with_plots

        query_params["user"] = request.user
        buildings = list_bdgs(query_params)

        paginator = OGCApiPagination()
        paginated_buildings = paginator.paginate_queryset(buildings, request)
        serializer = BuildingGeoJSONSerializer(
            paginated_buildings, with_plots=with_plots, many=True
        )

        return paginator.get_paginated_response(serializer.data)


class OGCSingleBuildingItemView(OGCAPIBaseView):

    renderer_classes = [GeoJSONRenderer, JSONRenderer]

    @rnb_doc(
        {
            "get": {
                "summary": "Récupérer un bâtiment par son ID-RNB",
                "description": "Récupère un seul bâtiment en tant que Feature GeoJSON.",

                "parameters": [
                    {
                        "name": "featureId",
                        "in": "path",
                        "required": True,
                        "description": "ID-RNB du bâtiment (rnb_id).",
                        "schema": {"type": "string"},
                    }
                        "description": "ID-RNB du bâtiment (rnb_id).",
                "responses": {
                    "200": {
                        "description": "Le bâtiment RNB au format GeoJSON.",
                        "content": {
                            "application/geo+json": {
                                "schema": {
                                    "$ref": "#/components/schemas/BuildingGeoJSON"
                                }
                            }
                        },
                    },
                    "404": {"description": "Bâtiment non trouvé."},
                },
            }
        },
        schemes=["ogc"],
    )
    def get(self, request, featureId):

        # check if we need to include plots
        with_plots_param = request.query_params.get("withPlots", False)
        with_plots = with_plots_param == "1"

        qs = list_bdgs(
            {"user": request.user, "status": "all", "with_plots": with_plots},
            only_active=False,
        )
        building = get_object_or_404(qs, rnb_id=clean_rnb_id(featureId))

        serializer = BuildingGeoJSONSerializer(building, with_plots=with_plots)

        return Response(serializer.data)


class OGCOpenAPIDefinitionView(OGCAPIBaseView):

    renderer_classes = [OpenAPIRenderer, JSONRenderer]

    def get(self, request: Request, *args, **kwargs):
        schema = build_schema_ogc_endpoints(request)

        return Response(
            schema, content_type="application/vnd.oai.openapi+json;version=3.0"
        )
