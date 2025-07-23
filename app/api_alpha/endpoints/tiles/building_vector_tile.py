from api_alpha.endpoints.tiles.base import BaseVectorTileView
from api_alpha.utils.parse_boolean import parse_boolean
from batid.services.vector_tiles import bdgs_tiles_sql


class BuildingsVectorTileView(BaseVectorTileView):
    def build_sql(self, request, tile_params):
        only_active_and_real = parse_boolean(
            request.GET.get("only_active_and_real", "true")
        )
        return bdgs_tiles_sql(tile_params, "point", only_active_and_real)


class BuildingsShapeVectorTileView(BaseVectorTileView):
    def build_sql(self, request, tile_params):
        only_active_and_real = parse_boolean(
            request.GET.get("only_active_and_real", "true")
        )
        return bdgs_tiles_sql(tile_params, "shape", only_active_and_real)
