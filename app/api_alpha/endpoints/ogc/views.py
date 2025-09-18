from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from api_alpha.pagination import OGCApiPagination
from api_alpha.serializers.serializers import BuildingGeoJSONSerializer
from batid.list_bdg import list_bdgs
from batid.services.rnb_id import clean_rnb_id
from api_alpha.utils.logging_mixin import RNBLoggingMixin


class OGCAPIBaseView(APIView, RNBLoggingMixin):

    # NEW HELPER METHOD
    def _get_root_url(self, request: Request) -> str:
        """Constructs the root URL (e.g., 'http://testserver') from the request."""
        return f"{request.scheme}://{request.get_host()}"

    def _get_conformance_link(self, request: Request, is_currrent_page=False):

        root_url = self._get_root_url(request)
        return {
            "href": f"{root_url}/api/alpha/ogc/conformance/",
            "rel": "self" if is_currrent_page else "conformance",
            "type": "application/json",
            "title": "Les spécifications respectées par cette API",
        }

    def _get_collections_link(self, request: Request, is_currrent_page=False):

        root_url = self._get_root_url(request)
        return {
            "href": f"{root_url}/api/alpha/ogc/collections/",
            "rel": "self" if is_currrent_page else "data",
            "type": "application/json",
            "title": "Liste des types de données disponibles dans cette API",
        }

    def _get_buildings_collection_link(self, request: Request, is_currrent_page=False):

        root_url = self._get_root_url(request)
        return {
            "href": f"{root_url}/api/alpha/ogc/collections/buildings/",
            "rel": (
                "self" if is_currrent_page else "collection"
            ),  # Using 'collection' is more specific than 'data'
            "type": "application/json",
            "title": "Meta-données à propos de la liste des bâtiments disponibles dans le RNB",
        }

    def _get_buildings_items_link(self, request: Request, is_currrent_page=False):

        root_url = self._get_root_url(request)
        return {
            "href": f"{root_url}/api/alpha/ogc/collections/buildings/items/",
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

        root_url = self._get_root_url(request)
        return {
            "href": f"{root_url}/api/alpha/ogc/",
            "rel": "root",
            "type": "application/json",
            "title": "Racine de l'API du RNB",
        }

    def _get_api_definition_link(self, request: Request):

        root_url = self._get_root_url(request)
        return {
            "href": f"{root_url}/api/alpha/ogc/openapi/",
            "rel": "service-desc",
            "type": "application/vnd.oai.openapi+json;version=3.0",
            "title": "Définition OpenAPI de l'API OGC du RNB",
        }


class OGCIndexView(OGCAPIBaseView):
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

    def get(self, request, *args, **kwargs):
        data = {
            "conformsTo": [
                "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
                "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
            ]
        }
        return Response(data)


class OGCCollectionsView(OGCAPIBaseView):
    def get(self, request: Request, *args, **kwargs):
        # MODIFIED: Pass request to all link helpers
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
    def get(self, request: Request, *args, **kwargs):
        # MODIFIED: Pass request to the helper
        data = self._get_buildings_collection(request, is_currrent_page=True)
        return Response(data)


class OGCBuildingItemsView(OGCAPIBaseView):
    # No changes needed in this method as the pagination class
    # already has access to the request object to build its own links.
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

    def get(self, request, rnb_id):

        # check if we need to include plots
        with_plots_param = request.query_params.get("withPlots", False)
        with_plots = with_plots_param == "1"

        qs = list_bdgs(
            {"user": request.user, "status": "all", "with_plots": with_plots},
            only_active=False,
        )
        building = get_object_or_404(qs, rnb_id=clean_rnb_id(rnb_id))

        serializer = BuildingGeoJSONSerializer(building, with_plots=with_plots)

        return Response(serializer.data)


class OGCOpenAPIDefinitionView(OGCAPIBaseView):
    def get(self, request: Request, *args, **kwargs):
        root_url = self._get_root_url(request)
        schema = {
            "openapi": "3.0.0",
            "info": {
                "title": "RNB OGC API",
                "version": "1.0.0",
                "description": "API OGC du Registre National des Bâtiments",
            },
            "servers": [{"url": f"{root_url}/api/alpha/ogc"}],
            "paths": {
                "/": {
                    "get": {
                        "summary": "Landing page de l'API OGC",
                        "description": "Point d'entrée principal de l'API OGC, fournissant des liens vers les autres ressources.",
                        "tags": ["Capabilities"],
                        "responses": {
                            "200": {
                                "description": "Landing page",
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
                "/conformance": {
                    "get": {
                        "summary": "Déclaration de conformité de l'API",
                        "description": "Liste les classes de conformité OGC auxquelles cette API adhère.",
                        "tags": ["Capabilities"],
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
                "/collections": {
                    "get": {
                        "summary": "Liste des collections de données",
                        "description": "Fournit une liste des collections de données disponibles via cette API.",
                        "tags": ["Capabilities"],
                        "responses": {
                            "200": {
                                "description": "Liste des collections",
                            }
                        },
                    }
                },
                "/collections/buildings": {
                    "get": {
                        "summary": "Métadonnées de la collection de bâtiments",
                        "description": "Fournit des informations détaillées sur la collection de bâtiments.",
                        "tags": ["Data"],
                        "responses": {
                            "200": {
                                "description": "Métadonnées de la collection",
                            }
                        },
                    }
                },
                "/collections/buildings/items": {
                    "get": {
                        "summary": "Liste des bâtiments (items)",
                        "description": "Récupère une liste de bâtiments sous forme de FeatureCollection GeoJSON.",
                        "tags": ["Data"],
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "description": "Nombre maximum d'items à retourner.",
                                "schema": {"type": "integer", "default": 10},
                            },
                            {
                                "name": "bbox",
                                "in": "query",
                                "description": "Filtre géographique par Bounding Box.",
                                "schema": {"type": "string"},
                            },
                        ],
                        "responses": {
                            "200": {
                                "description": "Une FeatureCollection GeoJSON de bâtiments.",
                                "content": {
                                    "application/geo+json": {
                                        "schema": {"type": "object"}
                                    }
                                },
                            }
                        },
                    }
                },
                "/collections/buildings/items/{featureId}": {
                    "get": {
                        "summary": "Récupérer un bâtiment par son ID",
                        "description": "Récupère un seul bâtiment en tant que Feature GeoJSON.",
                        "tags": ["Data"],
                        "parameters": [
                            {
                                "name": "featureId",
                                "in": "path",
                                "required": True,
                                "description": "ID du bâtiment (rnb_id).",
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "Une Feature GeoJSON du bâtiment.",
                                "content": {
                                    "application/geo+json": {
                                        "schema": {"type": "object"}
                                    }
                                },
                            },
                            "404": {"description": "Bâtiment non trouvé."},
                        },
                    }
                },
            },
        }

        return Response(
            schema, content_type="application/vnd.oai.openapi+json;version=3.0"
        )
