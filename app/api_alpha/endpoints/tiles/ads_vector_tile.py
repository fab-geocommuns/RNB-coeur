from api_alpha.endpoints.tiles.base import BaseVectorTileView
from batid.services.vector_tiles import ads_tiles_sql


class ADSVectorTileView(BaseVectorTileView):
    def build_sql(self, request, tile_params):
        return ads_tiles_sql(tile_params)
