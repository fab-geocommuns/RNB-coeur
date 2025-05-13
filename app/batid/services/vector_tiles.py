from typing import TypedDict

from batid.models import Building
from batid.models import BuildingADS
from batid.models import Plot
from batid.services.bdg_status import BuildingStatus


class TileParams(TypedDict):
    x: int
    y: int
    zoom: int


class Envelope(TypedDict):
    xmin: float
    xmax: float
    ymin: float
    ymax: float


def get_real_buildings_status():
    return ", ".join(
        ["'" + status + "'" for status in BuildingStatus.REAL_BUILDINGS_STATUS]
    )


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
def tileToEnvelope(tile: TileParams) -> Envelope:
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
def envelopeToBoundsSQL(env: Envelope) -> str:
    DENSIFY_FACTOR = 4
    segSize = (env["xmax"] - env["xmin"]) / DENSIFY_FACTOR
    sql_tmpl = (
        "ST_Segmentize(ST_MakeEnvelope({xmin}, {ymin}, {xmax}, {ymax}, 3857),{segSize})"
    )
    return sql_tmpl.format(**env, segSize=segSize)


def envelopeToADSSQL(env):

    params = {
        "table": BuildingADS._meta.db_table,
        "srid": str(4326),
        "attrColumns": "ads.file_number as file_number, t.operation ",
        "geomColumn": "shape",
    }

    tbl = params.copy()
    tbl["env"] = envelopeToBoundsSQL(env)

    sql_tmpl = """
            WITH
            bounds AS (
                SELECT {env} AS geom,
                       {env}::box2d AS b2d
            ),
            mvtgeom AS (
                SELECT ST_AsMVTGeom(ST_Transform(t.{geomColumn}, 3857), bounds.b2d) AS geom,
                       {attrColumns}
                FROM {table} t
                LEFT JOIN batid_ads ads ON t.ads_id = ads.id, bounds
                WHERE ST_Intersects(t.{geomColumn}, ST_Transform(bounds.geom, {srid}))
            )
            SELECT ST_AsMVT(mvtgeom.*) FROM mvtgeom
        """
    return sql_tmpl.format(**tbl)


def envelopeToPlotsSQL(env):
    params = {
        "table": Plot._meta.db_table,
        "srid": str(4326),
        "attrColumns": "id, regexp_replace(id, '^.*[A-Za-z]0?', '') AS plot_number ",
        "geomColumn": "shape",
    }

    tbl = params.copy()
    tbl["env"] = envelopeToBoundsSQL(env)

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


# Generate a SQL query to pull a tile worth of MVT data
# from the table of interest.
def envelopeToBuildingsSQL(
    env: Envelope, geometry_column: str, only_active_and_real: bool = True
) -> str:
    params = {
        "table": Building._meta.db_table,
        "srid": str(4326),
        "attrColumns": "rnb_id",
    }
    params["geomColumn"] = geometry_column

    tbl = params.copy()
    tbl["env"] = envelopeToBoundsSQL(env)
    tbl["active_clause"] = "AND t.is_active = true" if only_active_and_real else ""
    tbl["status_clause"] = (
        "AND t.status IN ({status})".format(status=get_real_buildings_status())
        if only_active_and_real
        else ""
    )
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
                   {attrColumns}, (select count(*) from batid_contribution c where c.rnb_id = t.rnb_id and c.status = 'pending') as contributions,
                   t.is_active AS is_active,
                   t.status AS status
            FROM {table} t, bounds
            WHERE ST_Intersects(t.{geomColumn}, ST_Transform(bounds.geom, {srid}))
            {active_clause}
            {status_clause}
        )
        SELECT ST_AsMVT(mvtgeom.*) FROM mvtgeom
    """
    return sql_tmpl.format(**tbl)


def url_params_to_tile(x: str, y: str, z: str) -> TileParams:
    tile: TileParams = {"x": int(x), "y": int(y), "zoom": int(z)}

    if not tileIsValid(tile):
        raise ValueError("Invalid tile coordinates")

    return tile


def bdgs_tiles_sql(tile: TileParams, data_type: str, only_active_and_real: bool) -> str:
    env = tileToEnvelope(tile)
    if data_type == "shape":
        geometry_column = "shape"
    elif data_type == "point":
        geometry_column = "point"
    sql = envelopeToBuildingsSQL(env, geometry_column, only_active_and_real)

    return sql


def ads_tiles_sql(tile):
    env = tileToEnvelope(tile)
    sql = envelopeToADSSQL(env)

    return sql


def plots_tiles_sql(tile):
    env = tileToEnvelope(tile)
    sql = envelopeToPlotsSQL(env)

    return sql
