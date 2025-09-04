from datetime import datetime
from datetime import timezone

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction
from rest_framework import status as http_status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.exceptions import BadRequest
from api_alpha.exceptions import ServiceUnavailable
from api_alpha.pagination import BuildingCursorPagination
from api_alpha.permissions import ReadOnly
from api_alpha.permissions import RNBContributorPermission
from api_alpha.serializers.serializers import BuildingCreateSerializer
from api_alpha.serializers.serializers import BuildingSerializer
from api_alpha.serializers.serializers import BuildingGeoJSONSerializer
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import get_status_html_list
from api_alpha.utils.rnb_doc import get_status_list
from api_alpha.utils.rnb_doc import rnb_doc
from batid.exceptions import BANAPIDown
from batid.exceptions import BANBadResultType
from batid.exceptions import BANUnknownCleInterop
from batid.exceptions import InvalidOperation
from batid.list_bdg import list_bdgs
from batid.models import Building
from batid.models import Contribution


class ListCreateBuildings(RNBLoggingMixin, APIView):
    permission_classes = [ReadOnly | RNBContributorPermission]

    @rnb_doc(
        {
            "get": {
                "summary": "Liste des batiments",
                "description": (
                    "Cet endpoint permet de récupérer une liste paginée de bâtiments. "
                    "Des filtres, notamment par code INSEE de la commune, sont disponibles. NB : l'URL se termine nécessairement par un slash (/)."
                ),
                "operationId": "listBuildings",
                "parameters": [
                    {
                        "name": "insee_code",
                        "in": "query",
                        "description": "Filtre les bâtiments dont l'emprise au sol est située dans les limites géographiques de la commune ayant ce code INSEE.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "75101",
                    },
                    {
                        "name": "status",
                        "in": "query",
                        "description": f"Filtre les bâtiments par statut. Il est possible d'utiliser plusieurs valeurs séparées par des virgules. Les valeurs possibles sont : <br /><br /> {get_status_html_list()}<br />",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "constructed,demolished",
                    },
                    {
                        "name": "cle_interop_ban",
                        "in": "query",
                        "description": "Filtre les bâtiments associés à cette clé d'interopérabilité BAN.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "94067_7115_00073",
                    },
                    {
                        "name": "bb",
                        "in": "query",
                        "description": (
                            "Filtre les bâtiments dont l'emprise au sol est située dans la bounding box"
                            "définie par les coordonnées Nord-Ouest et Sud-Est. Les coordonnées sont séparées par des virgules. "
                            "Le format est <code>nw_lat,nw_lng,se_lat,se_lng</code> où : <br/>"
                            "<ul>"
                            "<li><b>nw_lat</b> : latitude du point Nord Ouest de la bounding box</li>"
                            "<li><b>nw_lng</b> : longitude du point Nord Ouest de la bounding box</li>"
                            "<li><b>se_lat</b> : latitude du point Sud Est de la bounding box</li>"
                            "<li><b>se_lng</b> : longitude du point Sud Est de la bounding box</li>"
                            "</ul><br />"
                        ),
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "48.845782,2.424525,48.839201,2.434158",
                    },
                    {
                        "name": "withPlots",
                        "in": "query",
                        "description": "Inclure les parcelles intersectant les bâtiments de la réponse. Valeur attendue : 1. Chaque parcelle associée intersecte le bâtiment correspondant. Elle contient son identifiant ainsi que le taux de couverture du bâtiment.",
                        "required": False,
                        "schema": {
                            "type": "boolean",
                            "default": False,
                        },
                        "example": "1",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée de bâtiments",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "next": {
                                            "type": "string",
                                            "description": "<br />URL de la page de résultats suivante<br />",
                                            "nullable": True,
                                            "example": f"{settings.URL}/api/alpha/buildings/?cursor=cD02MzQ3OTk1",
                                        },
                                        "previous": {
                                            "type": "string",
                                            "description": "<br />URL de la page de résultats précédente<br />",
                                            "nullable": True,
                                            "example": f"{settings.URL}/api/alpha/buildings/?cursor=hFG78YEdFR",
                                        },
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "allOf": [
                                                    {
                                                        "$ref": "#/components/schemas/Building"
                                                    },
                                                    {
                                                        "$ref": "#/components/schemas/BuildingWPlots"
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
            },
        },
    )
    def get(self, request: Request) -> Response:
        query_params = request.query_params.dict()

        # check if we need to include plots
        with_plots_param = request.query_params.get("withPlots", None)
        with_plots = True if with_plots_param == "1" else False
        query_params["with_plots"] = with_plots

        # add user to query params
        query_params["user"] = request.user
        buildings = list_bdgs(query_params)
        paginator = BuildingCursorPagination()

        # paginate
        paginated_buildings = paginator.paginate_queryset(buildings, request)

        # get the "format" query parameter
        format_param = request.query_params.get("format", "json").lower()

        if format_param == "geojson":
            serializer = BuildingGeoJSONSerializer(
                paginated_buildings, with_plots=with_plots, many=True
            )
        else:
            serializer = BuildingSerializer(
                paginated_buildings, with_plots=with_plots, many=True
            )

        return paginator.get_paginated_response(serializer.data)

    @rnb_doc(
        {
            "post": {
                "summary": "Création d'un bâtiment",
                "description": "Cet endpoint permet de créer un bâtiment dans le RNB. Lors de la création, un identifiant RNB (ID-RNB) est généré. L'utilisateur doit être identifié et disposer des droits nécessaires pour écrire dans le RNB.",
                "operationId": "postBuilding",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "comment": {
                                        "type": "string",
                                        "description": "Commentaire optionnel associé à la création du bâtiment.",
                                        "example": "Bâtiment ajouté suite à une nouvelle construction, visible sur la vue satellite.",
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": get_status_list(),
                                        "description": "Statut du bâtiment.",
                                        "example": "constructed",
                                    },
                                    "addresses_cle_interop": {
                                        "type": "array",
                                        # currently a bug in gitbook, addding info on items hides the description
                                        # "items": {"type": "string"},
                                        "description": "Liste des clés d'interopérabilité BAN liées au bâtiment.",
                                        "example": [
                                            "75105_8884_00004",
                                            "75105_8884_00006",
                                        ],
                                    },
                                    "shape": {
                                        "type": "string",
                                        "description": "Géométrie du bâtiment au format WKT ou HEX, en WGS84. La géométrie attendue est idéalement un polygone représentant le bâtiment, mais il est également possible de ne donner qu'un point.",
                                        "example": "POLYGON((2.3522 48.8566, 2.3532 48.8567, 2.3528 48.857, 2.3522 48.8566))",
                                    },
                                },
                                "required": [
                                    "status",
                                    "shape",
                                    "addresses_cle_interop",
                                ],
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Détails du bâtiment nouvellement créé dans le RNB",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "allOf": [
                                        {"$ref": "#/components/schemas/Building"},
                                        {"$ref": "#/components/schemas/BuildingWPlots"},
                                    ]
                                }
                            }
                        },
                    },
                    "403": {
                        "description": "L'utilisateur n'a pas les droits nécessaires pour créer un bâtiment."
                    },
                    "503": {"description": "Service temporairement indisponible"},
                    "404": {
                        "description": "Une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
                    },
                },
            }
        }
    )
    def post(self, request: Request) -> Response:
        input_serializer = BuildingCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        data = input_serializer.data
        user = request.user

        with transaction.atomic():
            # create a contribution
            contribution = Contribution(
                text=data.get("comment"),
                status="fixed",
                status_changed_at=datetime.now(timezone.utc),
                report=False,
                review_user=user,
            )
            contribution.save()

            event_origin = {
                "source": "contribution",
                "contribution_id": contribution.id,
            }

            status = data.get("status")
            addresses_cle_interop = data.get("addresses_cle_interop")
            shape = GEOSGeometry(data.get("shape"))

            addresses_id = list(set(addresses_cle_interop))

            try:
                created_building = Building.create_new(
                    user=user,
                    event_origin=event_origin,
                    status=status,
                    addresses_id=addresses_id,
                    shape=shape,
                    ext_ids=[],
                )
            except BANAPIDown:
                raise ServiceUnavailable(detail="BAN API is currently down")
            except BANUnknownCleInterop:
                raise NotFound(detail="Cle d'intéropérabilité not found on the BAN API")
            except BANBadResultType:
                raise BadRequest(
                    detail="BAN result has not the expected type (must be 'numero')"
                )
            except InvalidOperation as e:
                raise BadRequest(detail=e.api_message_with_details())

            # update the contribution now that the rnb_id is known
            contribution.rnb_id = created_building.rnb_id
            contribution.save()

        output_serializer = BuildingSerializer(created_building, with_plots=True)
        return Response(output_serializer.data, status=http_status.HTTP_201_CREATED)
