class ADSVectorTileView(APIView):
    def get(self, request, x, y, z):

        # might do : include a minimum zoom level as it is done for buildings
        tile_dict = url_params_to_tile(x, y, z)
        sql = ads_tiles_sql(tile_dict)

        with connection.cursor() as cursor:
            cursor.execute(sql)
            tile_file = cursor.fetchone()[0]

        return HttpResponse(
            tile_file, content_type="application/vnd.mapbox-vector-tile"
        )


class PlotsVectorTileView(APIView):
    def get(self, request, x, y, z):

        if int(z) >= 16:

            tile_dict = url_params_to_tile(x, y, z)
            sql = plots_tiles_sql(tile_dict)

            with connection.cursor() as cursor:
                cursor.execute(sql)
                tile_file = cursor.fetchone()[0]

            return HttpResponse(
                tile_file, content_type="application/vnd.mapbox-vector-tile"
            )
        else:
            return HttpResponse(status=204)


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
