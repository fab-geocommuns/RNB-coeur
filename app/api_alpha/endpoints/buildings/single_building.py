from datetime import datetime

from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status as http_status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.apps import LiteralStr
from api_alpha.exceptions import BadRequest
from api_alpha.exceptions import ServiceUnavailable
from api_alpha.permissions import ReadOnly
from api_alpha.permissions import RNBContributorPermission
from api_alpha.serializers.building_history import BuildingHistorySerializer
from api_alpha.serializers.serializers import BuildingGeoJSONSerializer
from api_alpha.serializers.serializers import BuildingSerializer
from api_alpha.serializers.serializers import BuildingUpdateSerializer
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import get_status_list
from api_alpha.utils.rnb_doc import rnb_doc
from batid.exceptions import BANAPIDown
from batid.exceptions import BANBadResultType
from batid.exceptions import BANUnknownCleInterop
from batid.exceptions import InvalidOperation
from batid.list_bdg import list_bdgs
from batid.models import Building
from batid.models import Contribution
from batid.services.bdg_history import get_bdg_history
from batid.services.rnb_id import clean_rnb_id


class SingleBuildingHistory(APIView):
    def get(self, request, rnb_id):

        # check the building exists
        get_object_or_404(Building, rnb_id=clean_rnb_id(rnb_id))

        rows = get_bdg_history(rnb_id=rnb_id)

        serializer = BuildingHistorySerializer(rows, many=True)

        return Response(serializer.data)


class SingleBuilding(RNBLoggingMixin, APIView):
    permission_classes = [ReadOnly | RNBContributorPermission]

    @rnb_doc(
        {
            "get": {
                "summary": "Consultation d'un bâtiment",
                "description": "Cet endpoint permet de récupérer l'ensemble des attributs d'un bâtiment à partir de son identifiant RNB. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "getBuilding",
                "parameters": [
                    {
                        "name": "rnb_id",
                        "in": "path",
                        "description": "Identifiant unique du bâtiment dans le RNB (ID-RNB)",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "PG46YY6YWCX8",
                    },
                    {
                        "name": "withPlots",
                        "in": "query",
                        "description": "Inclure les parcelles intersectant le bâtiment. Valeur attendue : 1. Chaque parcelle associée intersecte le bâtiment correspondant. Elle contient son identifiant ainsi que le taux de couverture du bâtiment par cette parcelle.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "1",
                    },
                    {
                        "name": "format",
                        "in": "query",
                        "description": "Format de la réponse. Valeurs possibles : `json` (par défaut) ou `geojson`. En format `geojson`, la réponse est un objet de type Feature tel que défini dans le standard GeoJSON.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "geojson",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Détails du bâtiment",
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
                    }
                },
            }
        }
    )
    def get(self, request, rnb_id):

        # check if we need to include plots
        with_plots_param = request.query_params.get("withPlots", False)
        with_plots = with_plots_param == "1"

        qs = list_bdgs(
            {"user": request.user, "status": "all", "with_plots": with_plots},
            only_active=False,
        )
        building = get_object_or_404(qs, rnb_id=clean_rnb_id(rnb_id))

        # get the "format" query parameter
        format_param = request.query_params.get("format", "json").lower()

        if format_param == "geojson":
            serializer = BuildingGeoJSONSerializer(building, with_plots=with_plots)
        else:
            serializer = BuildingSerializer(building, with_plots=with_plots)

        return Response(serializer.data)

    @rnb_doc(
        {
            "patch": {
                "summary": "Mise à jour ou désactivation/réactivation d'un bâtiment",
                "description": LiteralStr(
                    """\
Cet endpoint permet de :
* mettre à jour un bâtiment existant (status, addresses_cle_interop, shape)
* désactiver son ID-RNB s'il s'avère qu'il ne devrait pas faire partie du
  RNB. Par exemple un arbre qui aurait été par erreur répertorié comme un
  bâtiment du RNB.
* réactiver un ID-RNB, si celui-ci a été désactivé par erreur.

Il n'est pas possible de simultanément mettre à jour un bâtiment et de le désactiver/réactiver.

Cet endpoint nécessite d'être identifié et d'avoir des droits d'édition du RNB.

Exemples valides:
* ```{"comment": "faux bâtiment", "is_active": False}```
* ```{"comment": "RNB ID désactivé par erreur, on le réactive", "is_active": True}```
* ```{"comment": "bâtiment démoli", "status": "demolished"}```
* ```{"comment": "bâtiment en ruine", "status": "notUsable", "addresses_cle_interop": ["75105_8884_00004"]}```
"""
                ),
                "operationId": "patchBuilding",
                "parameters": [
                    {
                        "name": "rnb_id",
                        "in": "path",
                        "description": "Identifiant unique du bâtiment dans le RNB (ID-RNB)",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "PG46YY6YWCX8",
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "comment": {
                                        "type": "string",
                                        "description": "Texte associé à la modification et la justifiant.",
                                        "exemple": "Ce n'est pas un bâtiment mais un arbre.",
                                    },
                                    "is_active": {
                                        "type": "boolean",
                                        "description": LiteralStr(
                                            """\
* `False` : l' ID-RNB est désactivé, car sa présence dans le RNB est une erreur. Ne permet *pas* de signaler une démolition, qui doit se faire par une mise à jour du statut.
* `True` : l'ID-RNB est réactivé. À utiliser uniquement pour annuler une désactivation accidentelle."""
                                        ),
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": get_status_list(),
                                        "description": f"Statut du bâtiment.",
                                        "exemple": "demolished",
                                    },
                                    "addresses_cle_interop": {
                                        "type": "array",
                                        # currently a bug in gitbook, addding info on items hides the description
                                        # "items": {"type": "string"},
                                        "description": LiteralStr(
                                            """\
Liste des clés d'interopérabilité BAN liées au bâtiment.

Si ce paramêtre est :
* absent, alors les clés ne sont pas modifiées.
* présent et que sa valeur est une liste vide, alors le bâtiment ne sera plus lié à aucune adresse."""
                                        ),
                                        "exemple": [
                                            "75105_8884_00004",
                                            "75105_8884_00006",
                                        ],
                                    },
                                    "shape": {
                                        "type": "string",
                                        "description": """Géométrie du bâtiment au format WKT ou HEX, en WGS84. La géometrie attendue est idéalement un polygone représentant le bâtiment, mais il est également possible de ne donner qu'un point.""",
                                    },
                                },
                                "required": [],
                            }
                        }
                    },
                },
                "responses": {
                    "204": {
                        "description": "Pas de contenu attendu dans la réponse en cas de succès",
                    },
                    "400": {
                        "description": "Requête invalide (données mal formatées ou incomplètes)."
                    },
                    "403": {
                        "description": "L'utilisateur n'a pas les droits nécessaires pour créer un bâtiment."
                    },
                    "503": {"description": "Service temporairement indisponible"},
                    "404": {
                        "description": "ID-RNB inconnu ou une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
                    },
                },
            }
        }
    )
    def patch(self, request, rnb_id):
        serializer = BuildingUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.data
        user = request.user
        building = get_object_or_404(Building, rnb_id=rnb_id)

        with transaction.atomic():
            contribution = Contribution(
                rnb_id=rnb_id,
                text=data.get("comment"),
                status="fixed",
                status_changed_at=datetime.now(),
                review_user=user,
                report=False,
            )
            contribution.save()

            event_origin = {
                "source": "contribution",
                "contribution_id": contribution.id,
            }

            try:
                if data.get("is_active") == False:
                    # a building that is not a building has its RNB ID deactivated from the base
                    building.deactivate(user, event_origin)
                elif data.get("is_active") == True:
                    # a building is reactivated, after a deactivation that should not have
                    building.reactivate(user, event_origin)
                else:
                    status = data.get("status")
                    addresses_cle_interop = data.get("addresses_cle_interop")

                    addresses_id = None
                    if isinstance(addresses_cle_interop, list):
                        addresses_id = list(set(addresses_cle_interop))

                    shape = (
                        GEOSGeometry(data.get("shape")) if data.get("shape") else None
                    )
                    building.update(
                        user,
                        event_origin,
                        status,
                        addresses_id,
                        shape=shape,
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

        # request is successful, no content to send back
        return Response(status=http_status.HTTP_204_NO_CONTENT)
