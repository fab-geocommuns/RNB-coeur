from django.conf import settings
from django.db import connection

from batid.models import Building

TABLE = {
    "table": Building._meta.db_table,
    "srid": str(settings.DEFAULT_SRID),
    "geomColumn": "point",
    "attrColumns": "rnb_id",
}


def tileIsValid(tile):
    if not ("x" in tile and "y" in tile and "zoom" in tile):
        return False
    if "format" not in tile or tile["format"] not in ["pbf", "mvt"]:
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


# # Run tile query SQL and return error on failure conditions
# def sqlToPbf(self, sql):
#     # Make and hold connection to database
#     if not self.DATABASE_CONNECTION:
#         try:
#             self.DATABASE_CONNECTION = psycopg2.connect(**DATABASE)
#         except (Exception, psycopg2.Error) as error:
#             self.send_error(500, "cannot connect: %s" % (str(DATABASE)))
#             return None
#
#     # Query for MVT
#     with self.DATABASE_CONNECTION.cursor() as cur:
#         cur.execute(sql)
#         if not cur:
#             self.send_error(404, "sql query failed: %s" % (sql))
#             return None
#         return cur.fetchone()[0]
#
#     return None


def one_shot(x, y, z):
    x = int(x)
    y = int(y)
    z = int(z)

    q = (
        "SELECT ST_AsMVT(q, 'bdg', 4096, 'point') "
        "FROM ("
        "SELECT rnb_id, ST_AsMvtGeom("
        "point, "
        "BBox(%(x)s, %(y)s, %(z)s), "
        "4096,"
        "256,"
        "true"
        ") AS geom "
        "FROM batid_building "
        "WHERE ST_Intersects(point, BBox(%(x)s, %(y)s, %(z)s))"
        ") as q"
    )

    params = {"x": x, "y": y, "z": z}

    with connection.cursor() as cursor:
        cursor.execute(q, params)
        return cursor.fetchone()
