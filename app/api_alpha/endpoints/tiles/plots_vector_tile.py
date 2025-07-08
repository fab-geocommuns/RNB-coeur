from django.db import connection
from django.http import HttpResponse
from rest_framework.views import APIView

from batid.services.vector_tiles import plots_tiles_sql
from batid.services.vector_tiles import url_params_to_tile


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
