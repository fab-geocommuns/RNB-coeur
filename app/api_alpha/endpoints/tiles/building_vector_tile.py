from django.db import connection
from django.http import HttpResponse
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import OpenApiResponse
from rest_framework.views import APIView
from api_alpha.utils.parse_boolean import parse_boolean
from batid.services.vector_tiles import bdgs_tiles_sql
from batid.services.vector_tiles import url_params_to_tile


class BuildingsVectorTileView(APIView):
    @extend_schema(
        tags=["Tile"],
        operation_id="get_vector_tile",
        summary="Obtenir une tuile vectorielle",
        description=(
            "Cette API fournit des tuiles vectorielles au format PBF permettant d'intégrer les bâtiments "
            "du Référentiel National des Bâtiments (RNB) dans une cartographie. Chaque tuile contient des points "
            "représentant des bâtiments avec un attribut 'rnb_id'. Les tuiles sont utilisables avec un niveau de zoom "
            "minimal de 16 et peuvent être intégrées dans des outils comme QGIS ou des sites web."
        ),
        auth=[],
        parameters=[
            OpenApiParameter(
                name="x",
                description="Coordonnée X de la tuile",
                required=True,
                type=int,
                location=OpenApiParameter.PATH,
            ),
            OpenApiParameter(
                name="y",
                description="Coordonnée Y de la tuile",
                required=True,
                type=int,
                location=OpenApiParameter.PATH,
            ),
            OpenApiParameter(
                name="z",
                description="Niveau de zoom de la tuile",
                required=True,
                type=int,
                location=OpenApiParameter.PATH,
            ),
            OpenApiParameter(
                name="only_active",
                description="Filtrer les bâtiments actifs",
                required=False,
                type=bool,
                default=True,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="Fichier PBF contenant les tuiles vectorielles",
            ),
            400: {"description": "Requête invalide"},
        },
    )
    def get(self, request, x, y, z):
        only_active_and_real_param = request.GET.get("only_active_and_real", "true")
        only_active_and_real = parse_boolean(only_active_and_real_param)

        # Check the request zoom level
        if int(z) >= 16:
            tile_dict = url_params_to_tile(x, y, z)
            sql = bdgs_tiles_sql(tile_dict, "point", only_active_and_real)

            with connection.cursor() as cursor:
                cursor.execute(sql)
                tile_file = cursor.fetchone()[0]

            return HttpResponse(
                tile_file, content_type="application/vnd.mapbox-vector-tile"
            )
        else:
            return HttpResponse(status=204)


def get_tile_shape(request, x, y, z):
    only_active_and_real_param = request.GET.get("only_active_and_real", "true")
    only_active_and_real = parse_boolean(only_active_and_real_param)

    # Check the request zoom level
    if int(z) >= 16:
        tile_dict = url_params_to_tile(x, y, z)
        sql = bdgs_tiles_sql(tile_dict, "shape", only_active_and_real)

        with connection.cursor() as cursor:
            cursor.execute(sql)
            tile_file = cursor.fetchone()[0]

        return HttpResponse(
            tile_file, content_type="application/vnd.mapbox-vector-tile"
        )
    else:
        return HttpResponse(status=204)
