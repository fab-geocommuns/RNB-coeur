from django.db import connection
from django.http import HttpResponse
from rest_framework.views import APIView

from batid.services.vector_tiles import ads_tiles_sql
from batid.services.vector_tiles import url_params_to_tile


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
