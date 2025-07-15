from abc import abstractmethod

from django.db import connection
from django.http import HttpResponse
from rest_framework.request import Request
from rest_framework.views import APIView

from batid.services.vector_tiles import TileParams


class BaseVectorTileView(APIView):
    min_zoom = 16
    max_zoom = 30
    content_type = "application/vnd.mapbox-vector-tile"

    def get(self, request, x, y, z):
        z = int(z)
        if z < self.min_zoom or z > self.max_zoom:
            return HttpResponse(status=204)

        tile_params = self._url_params_to_tile(x, y, z)
        sql = self.build_sql(request, tile_params)
        tile = self._exec_sql(sql)
        return HttpResponse(tile, content_type=self.content_type)

    def _exec_sql(self, sql):
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchone()[0]

    def _url_params_to_tile(self, x: str, y: str, z: str) -> TileParams:
        tile: TileParams = {"x": int(x), "y": int(y), "zoom": int(z)}

        if not self._tile_is_valid(tile):
            raise ValueError("Invalid tile coordinates")

        return tile

    def _tile_is_valid(self, tile: TileParams) -> bool:
        if not ("x" in tile and "y" in tile and "zoom" in tile):
            return False
        if not (
            isinstance(tile["x"], int)
            and isinstance(tile["y"], int)
            and isinstance(tile["zoom"], int)
        ):
            return False
        size = 2 ** tile["zoom"]
        if tile["x"] >= size or tile["y"] >= size:
            return False
        if tile["x"] < 0 or tile["y"] < 0:
            return False
        return True

    @abstractmethod
    def build_sql(self, request: Request, tile_params: TileParams) -> str:
        pass
