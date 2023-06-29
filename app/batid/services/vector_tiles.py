from typing import Generator

import math
from django.conf import settings
from django.db import connection

from batid.models import Building, Department
from batid.services.france import get_metropolitan_bbox
from batid.utils.db import dictfetchone

TABLE = {
    "table": Building._meta.db_table,
    "srid": str(settings.DEFAULT_SRID),
    "geomColumn": "point",
    "attrColumns": "rnb_id",
}


def tileIsValid(tile):
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


# Calculate envelope in "Spherical Mercator" (https://epsg.io/3857)
def tileToEnvelope(tile):
    # Width of world in EPSG:3857
    worldMercMax = 20037508.3427892
    worldMercMin = -1 * worldMercMax
    worldMercSize = worldMercMax - worldMercMin
    # Width in tiles
    worldTileSize = 2 ** tile["zoom"]
    # Tile width in EPSG:3857
    tileMercSize = worldMercSize / worldTileSize
    # Calculate geographic bounds from tile coordinates
    # XYZ tile coordinates are in "image space" so origin is
    # top-left, not bottom right
    env = dict()
    env["xmin"] = worldMercMin + tileMercSize * tile["x"]
    env["xmax"] = worldMercMin + tileMercSize * (tile["x"] + 1)
    env["ymin"] = worldMercMax - tileMercSize * (tile["y"] + 1)
    env["ymax"] = worldMercMax - tileMercSize * (tile["y"])
    return env


# Generate SQL to materialize a query envelope in EPSG:3857.
# Densify the edges a little so the envelope can be
# safely converted to other coordinate systems.
def envelopeToBoundsSQL(env):
    DENSIFY_FACTOR = 4
    env["segSize"] = (env["xmax"] - env["xmin"]) / DENSIFY_FACTOR
    sql_tmpl = (
        "ST_Segmentize(ST_MakeEnvelope({xmin}, {ymin}, {xmax}, {ymax}, 3857),{segSize})"
    )
    return sql_tmpl.format(**env)


# Generate a SQL query to pull a tile worth of MVT data
# from the table of interest.
def envelopeToSQL(env):
    tbl = TABLE.copy()
    tbl["env"] = envelopeToBoundsSQL(env)
    # Materialize the bounds
    # Select the relevant geometry and clip to MVT bounds
    # Convert to MVT format
    sql_tmpl = """
        WITH 
        bounds AS (
            SELECT {env} AS geom, 
                   {env}::box2d AS b2d
        ),
        mvtgeom AS (
            SELECT ST_AsMVTGeom(ST_Transform(t.{geomColumn}, 3857), bounds.b2d) AS geom, 
                   {attrColumns}
            FROM {table} t, bounds
            WHERE ST_Intersects(t.{geomColumn}, ST_Transform(bounds.geom, {srid}))
        ) 
        SELECT ST_AsMVT(mvtgeom.*) FROM mvtgeom
    """
    return sql_tmpl.format(**tbl)


def url_params_to_tile(x, y, z):
    tile = {"x": int(x), "y": int(y), "zoom": int(z)}

    if not tileIsValid(tile):
        raise ValueError("Invalid tile coordinates")

    return tile


def tile_sql(tile):
    env = tileToEnvelope(tile)
    sql = envelopeToSQL(env)

    return sql


def generate_all_tiles():
    # get the enveloppe
    bbox = get_metropolitan_bbox()

    print("--- bbox ---")
    print(bbox)

    z_range = get_zoom_range()

    tiles_coords = tiles_in_bbox(bbox, z_range)

    # print(bbox)
    # print(type(bbox))
    # get all tiles coordinates
    # for each tile query the pbf format from the database
    # save the file in the tiles folder

    pass


# Convert à latitude, longitude pair to a tile coordinate for a given zoom level
def latlng_to_tile_xy(lat: float, lng: float, zoom: int) -> tuple:
    lat_rad = math.radians(lat)
    n = 2.0**zoom
    xtile = int((lng + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)


def get_zoom_range() -> range:
    min_zoom = settings.VCTR_TILES_MIN_ZOOM
    max_zoom = settings.VCTR_TILES_MAX_ZOOM

    return range(min_zoom, max_zoom + 1)


def tiles_in_bbox(bbox: dict, zoom_range: range):
    t_count = 0

    for z in zoom_range:
        print("--- zoom : ", z)

        min_tile_x, max_tile_y = latlng_to_tile_xy(bbox["y_min"], bbox["x_min"], z)
        max_tile_x, min_tile_y = latlng_to_tile_xy(bbox["y_max"], bbox["x_max"], z)

        x_diff = max_tile_x - min_tile_x
        y_diff = max_tile_y - min_tile_y

        z_t_count = x_diff * y_diff
        print(f"-- z level : {z} - {z_t_count:,} tiles")

        t_count += x_diff * y_diff

    print(f"--- total tiles : {t_count:,}")

    # for x in range(min_tile_x, max_tile_x + 1):
    #     for y in range(min_tile_y, max_tile_y + 1):
    #         yield x, y, z
