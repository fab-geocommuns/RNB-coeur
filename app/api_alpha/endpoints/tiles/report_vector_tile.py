from rest_framework.request import Request

from api_alpha.endpoints.tiles.base import BaseVectorTileView
from batid.services.vector_tiles import reports_tiles_sql
from batid.services.vector_tiles import TileParams


class ReportVectorTileView(BaseVectorTileView):
    min_zoom = 0

    def build_sql(self, request: Request, tile_params: TileParams) -> str:
        return reports_tiles_sql(tile_params)
