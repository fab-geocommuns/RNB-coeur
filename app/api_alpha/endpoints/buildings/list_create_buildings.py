from typing import Any, cast

from api_alpha.apps import LiteralStr
from api_alpha.exceptions import BadRequest, ServiceUnavailable
from api_alpha.pagination import BuildingListingCursorPagination, OGCApiPagination
from api_alpha.permissions import ReadOnly, RNBContributorPermission
from api_alpha.serializers.serializers import (
    BuildingCreateSerializer,
    BuildingGeoJSONSerializer,
    BuildingSerializer,
    ListBuildingQuerySerializer,
)
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import (
    EDITION_AUTH_RESPONSES,
    get_shape_rules,
    get_status_html_list,
    get_status_list,
    rnb_doc,
)
from batid.exceptions import (
    BANAPIDown,
    BANBadResultType,
    BANUnknownCleInterop,
    InvalidOperation,
)
from batid.list_bdg import list_bdgs
from batid.models import Building, Contribution, Trophy
from batid.services.bdg_status import BuildingStatus
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction
from rest_framework import status as http_status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

# Statuses listed by default, as markdown: `constructed` ou `notUsable`
REAL_STATUS_MD = " ou ".join(f"`{s}`" for s in BuildingStatus.REAL_BUILDINGS_STATUS)

# Response of the listing with format=json (default).
# The two formats share the application/json content type (the API never sends
# application/geo+json), hence "required" on both schemas to tell them apart in
# the oneOf of the response.
BUILDINGS_PAGE_SCHEMA = {
    "type": "object",
    "title": "format=json",
    "description": "Réponse par défaut, ou avec le paramètre `format=json`",
    "required": ["next", "previous", "results"],
    "properties": {
        "next": {
            "type": ["string", "null"],
            "description": "<br />URL de la page de résultats suivante<br />",
            "example": f"{settings.URL}/api/alpha/buildings/?cursor=cD02MzQ3OTk1",
        },
        "previous": {
            "type": ["string", "null"],
            "description": "<br />URL de la page de résultats précédente<br />",
            "example": f"{settings.URL}/api/alpha/buildings/?cursor=hFG78YEdFR",
        },
        "results": {
            "type": "array",
            "items": {
                "allOf": [
                    {"$ref": "#/components/schemas/Building"},
                    {"$ref": "#/components/schemas/BuildingWPlots"},
                ]
            },
        },
    },
}

# Response of the listing with format=geojson: the FeatureCollection is at the root
BUILDINGS_FEATURE_COLLECTION_SCHEMA = {
    "type": "object",
    "title": "format=geojson",
    "description": "Réponse avec le paramètre `format=geojson`",
    "required": ["type", "features", "links"],
    "properties": {
        "type": {"type": "string", "example": "FeatureCollection"},
        "features": {
            "type": "array",
            "items": {"$ref": "#/components/schemas/BuildingGeoJSON"},
        },
        "links": {
            "type": "array",
            "description": "Liens vers la page courante (`self`), la page suivante (`next`) et la page précédente (`prev`), quand elles existent.",
            "items": {
                "type": "object",
                "properties": {
                    "rel": {"type": "string", "enum": ["self", "next", "prev"]},
                    "title": {"type": "string"},
                    "type": {"type": "string", "example": "application/geo+json"},
                    "href": {"type": "string"},
                },
            },
        },
        "numberReturned": {
            "type": "integer",
            "description": "Nombre de bâtiments dans cette page.",
            "example": 20,
        },
        "timeStamp": {
            "type": "string",
            "format": "date-time",
            "description": "Horodatage de la génération de la réponse.",
            "example": "2025-12-25T13:37:00Z",
        },
    },
}


class ListCreateBuildings(RNBLoggingMixin, APIView):
    permission_classes = [ReadOnly | RNBContributorPermission]

    @rnb_doc(
        {
            "get": {
                "summary": "Liste des batiments",
                "description": LiteralStr(f"""\
Cet endpoint permet de récupérer une liste paginée de bâtiments.

Au moins un de ces filtres est requis : `bbox`, `bb`, `insee_code` ou `cle_interop_ban`. Les autres paramètres ne suffisent pas.

Bâtiments renvoyés :
* seuls les bâtiments actifs sont listés. Un bâtiment désactivé reste accessible par la consultation d'un bâtiment ;
* sans paramètre `status`, seuls les bâtiments réels sont listés, c'est-à-dire de statut {REAL_STATUS_MD}.

Les filtres géographiques (`bbox`, `bb`, `insee_code`) portent sur le point du bâtiment, pas sur son emprise au sol.

NB : l'URL se termine nécessairement par un slash (/).
"""),
                "operationId": "listBuildings",
                "parameters": [
                    {
                        "name": "insee_code",
                        "in": "query",
                        "description": "Filtre les bâtiments dont le point (localisation) intersecte la commune ayant ce code INSEE. Un code INSEE inconnu renvoie une erreur 404.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "75101",
                    },
                    {
                        "name": "status",
                        "in": "query",
                        "description": f"Filtre les bâtiments par statut. Il est possible d'utiliser plusieurs valeurs séparées par des virgules. Les valeurs possibles sont : <br /><br /> {get_status_html_list()}<br />La valeur `all` renvoie tous les statuts et ne se combine pas avec d'autres valeurs. Sans ce paramètre, seuls les bâtiments réels sont renvoyés ({', '.join(BuildingStatus.REAL_BUILDINGS_STATUS)}). Une valeur inconnue renvoie une erreur 400.",
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
                        "name": "withPlots",
                        "in": "query",
                        "description": """Liste les parcelles cadastrales intersectant le bâtiment. Pour chaque parcelle, il est donné la proportion de la surface du bâtiment située sur celle-ci. La valeur attendue pour ce paramêtre est `"1"`. """,
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "1",
                    },
                    {
                        "name": "format",
                        "in": "query",
                        "description": "Format de la réponse. Valeurs possibles : `json` (par défaut) ou `geojson`. En format `geojson`, la réponse est directement un objet de type FeatureCollection tel que défini dans le standard GeoJSON. La pagination se fait alors par l'attribut `links` (liens `next` et `prev`), et non par les attributs `next` et `previous`.",
                        "required": False,
                        "schema": {
                            "type": "string",
                            "default": "json",
                            "enum": ["json", "geojson"],
                        },
                        "example": "geojson",
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "description": "Nombre maximum de bâtiments à retourner dans la page de résultats. Valeur par défaut : 20. Valeur maximale : 100.",
                        "required": False,
                        "schema": {
                            "type": "integer",
                            "default": 20,
                            "maximum": 100,
                            "minimum": 1,
                        },
                        "example": 50,
                    },
                    {
                        "name": "bbox",
                        "in": "query",
                        "description": (
                            "Filtre les bâtiments dont le point (localisation) est situé dans la bounding box. "
                            "Le format est `min_lon,min_lat,max_lon,max_lat`. "
                            "La taille de la bbox est limitée par la contrainte (max_lon - min_lon) * (max_lat - min_lat) < 4. Cela correspond à la surface d'environ deux départements français."
                        ),
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "2.424525,48.839201,2.434158,48.845782",
                    },
                    {
                        "name": "bb",
                        "in": "query",
                        "description": (
                            "OBSOLÈTE - préférez le paramètre `bbox` "
                            "Filtre les bâtiments dont le point (localisation) est situé dans la bounding box "
                            "définie par les coordonnées Nord-Ouest et Sud-Est. Les coordonnées sont séparées par des virgules. "
                            "Le format est `nw_lat,nw_lon,se_lat,se_lon`. "
                            "La taille de la bbox est limitée par la contrainte (se_lon - nw_lon) * (nw_lat - se_lat) < 4. Cela correspond à la surface d'environ deux départements français."
                        ),
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "48.845782,2.424525,48.839201,2.434158",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée de bâtiments",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "oneOf": [
                                        BUILDINGS_PAGE_SCHEMA,
                                        BUILDINGS_FEATURE_COLLECTION_SCHEMA,
                                    ]
                                }
                            },
                        },
                    },
                    "404": {
                        "description": "Le code INSEE ne correspond à aucune commune."
                    },
                },
            },
        },
    )
    def get(self, request: Request) -> Response:
        query_serializer = ListBuildingQuerySerializer(data=request.query_params)

        if not query_serializer.is_valid():
            # Invalid data, return validation errors
            return Response(query_serializer.errors, status=400)

        query_params: dict[str, Any] = request.query_params.dict()

        # check if we need to include plots
        with_plots_param = request.query_params.get("withPlots", None)
        with_plots = True if with_plots_param == "1" else False
        query_params["with_plots"] = with_plots

        # add user to query params
        query_params["user"] = request.user
        buildings = list_bdgs(query_params)

        # paginate

        # get the "format" query parameter
        format_param = request.query_params.get("format", "json").lower()

        # Mypy annotations
        paginator: OGCApiPagination | BuildingListingCursorPagination
        serializer: BuildingGeoJSONSerializer | BuildingSerializer

        if format_param == "geojson":
            paginator = OGCApiPagination()
            paginated_buildings = paginator.paginate_queryset(buildings, request)
            serializer = BuildingGeoJSONSerializer(
                paginated_buildings, with_plots=with_plots, many=True
            )
        else:
            paginator = BuildingListingCursorPagination()
            paginated_buildings = paginator.paginate_queryset(buildings, request)
            serializer = BuildingSerializer(
                paginated_buildings, with_plots=with_plots, many=True
            )

        return paginator.get_paginated_response(serializer.data)

    @rnb_doc(
        {
            "post": {
                "summary": "Création d'un bâtiment",
                "description": LiteralStr(
                    "Cet endpoint permet de créer un bâtiment dans le RNB. Lors de la création, un identifiant RNB (ID-RNB) est généré. "
                    "L'utilisateur doit être identifié (en-tête `Authorization: Token <votre token>`) et disposer des droits nécessaires pour écrire dans le RNB.\n\n"
                    "La requête est refusée (400) si un champ obligatoire manque, si une clé d'interopérabilité ne fait pas entre 5 et 30 caractères "
                    "ou désigne autre chose qu'un numéro (voie, lieu-dit ou commune), ou si la géométrie ne respecte pas les règles décrites pour le champ `shape`."
                ),
                "operationId": "postBuilding",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "example": {
                                "comment": "nouveau bâtiment",
                                "status": "constructed",
                                "addresses_cle_interop": ["75105_8884_00004"],
                                "shape": "POLYGON((2.3522 48.8566, 2.3532 48.8567, 2.3528 48.857, 2.3522 48.8566))",
                            },
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
                                        "description": "Liste des clés d'interopérabilité BAN liées au bâtiment, éventuellement vide (`[]`) en l'absence d'adresse à attribuer. Chaque clé fait entre 5 et 30 caractères.",
                                        "example": [
                                            "75105_8884_00004",
                                            "75105_8884_00006",
                                        ],
                                    },
                                    "shape": {
                                        "type": "string",
                                        "description": LiteralStr(
                                            "Géométrie du bâtiment au format WKT ou HEX, en WGS84. La géométrie attendue est idéalement un polygone représentant le bâtiment, mais il est également possible de ne donner qu'un point.\n\nLa géométrie doit :\n"
                                            + get_shape_rules()
                                        ),
                                        "example": "POLYGON((2.3522 48.8566, 2.3532 48.8567, 2.3528 48.857, 2.3522 48.8566))",
                                    },
                                    "is_valid": {
                                        "type": "boolean",
                                        "default": False,
                                        "description": "Optionnel. Si `true`, le bâtiment est marqué comme valide dès sa création. L'utilisateur déclare ainsi que l'ensemble des informations liées aux bâtiments (statut, adresse, géométrie) sont valides. Vaut `false` par défaut, ce qui revient à simplement créer le bâtiment sans le valider.",
                                    },
                                },
                                "required": [
                                    "status",
                                    "shape",
                                    "addresses_cle_interop",
                                ],
                            },
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Détails du bâtiment nouvellement créé dans le RNB",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Building"}
                            }
                        },
                    },
                    "400": {
                        "description": "Requête invalide ou création refusée (voir les cas de refus dans la description)."
                    },
                    **EDITION_AUTH_RESPONSES,
                    "404": {
                        "description": "Une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
                    },
                    "503": {
                        "description": "Service temporairement indisponible (l'API de la BAN répond en erreur)"
                    },
                },
            }
        }
    )
    def post(self, request: Request) -> Response:
        input_serializer = BuildingCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        data = input_serializer.data
        # POST requires RNBContributorPermission, so the user is always authenticated
        user = cast(User, request.user)

        with transaction.atomic():
            # create a contribution
            contribution = Contribution(
                text=data.get("comment"),
                user=user,
            )
            contribution.save()

            event_origin = {
                "source": "contribution",
                "contribution_id": contribution.id,
            }

            # status and addresses_cle_interop are required fields (validated above)
            status = data["status"]
            addresses_cle_interop = data["addresses_cle_interop"]
            shape = GEOSGeometry(data.get("shape"))

            # remove possible duplicates
            addresses_cle_interop = list(set(addresses_cle_interop))

            try:
                created_building = Building.create_new(
                    user=user,
                    event_origin=event_origin,
                    status=status,
                    addresses_cle_interop=addresses_cle_interop,
                    shape=shape,
                    ext_ids=[],
                    is_valid=data.get("is_valid", False),
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

        output_serializer = BuildingSerializer(created_building)
        response_data = dict(output_serializer.data)
        # a validation may unlock new trophies; they are awarded in the database but
        # not returned here. The user retrieves them via the user trophies endpoint.
        if data.get("is_valid"):
            Trophy.check_and_award_all(user)
        return Response(response_data, status=http_status.HTTP_201_CREATED)
