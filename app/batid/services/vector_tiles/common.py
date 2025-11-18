from typing import TypedDict


class TileParams(TypedDict):
    x: int
    y: int
    zoom: int


class Envelope(TypedDict):
    xmin: float
    xmax: float
    ymin: float
    ymax: float


# Calculate envelope in "Spherical Mercator" (https://epsg.io/3857)
def tile_to_envelope(tile: TileParams) -> Envelope:
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
    xmin = worldMercMin + tileMercSize * tile["x"]
    ymin = worldMercMax - tileMercSize * (tile["y"] + 1)
    xmax = worldMercMin + tileMercSize * (tile["x"] + 1)
    ymax = worldMercMax - tileMercSize * (tile["y"])
    env: Envelope = {
        "xmin": xmin,
        "ymin": ymin,
        "xmax": xmax,
        "ymax": ymax,
    }
    return env


# Generate SQL to materialize a query envelope in EPSG:3857.
# Densify the edges a little so the envelope can be
# safely converted to other coordinate systems.
def envelope_to_bounds_sql(env: Envelope) -> str:
    DENSIFY_FACTOR = 4
    segSize = (env["xmax"] - env["xmin"]) / DENSIFY_FACTOR
    sql_tmpl = (
        "ST_Segmentize(ST_MakeEnvelope({xmin}, {ymin}, {xmax}, {ymax}, 3857),{segSize})"
    )
    return sql_tmpl.format(**env, segSize=segSize)
