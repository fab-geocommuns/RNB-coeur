from batid.services.vector_tiles import plots_tiles_sql
from api_alpha.endpoints.tiles.base import BaseVectorTileView


class PlotsVectorTileView(BaseVectorTileView):
    def build_sql(self, request, tile_params):
        return plots_tiles_sql(tile_params)
