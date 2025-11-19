from batid.models import BuildingADS
from batid.services.vector_tiles.common import envelope_to_bounds_sql
from batid.services.vector_tiles.common import tile_to_envelope


def envelope_to_ads_sql(env):

    params = {
        "table": BuildingADS._meta.db_table,
        "srid": str(4326),
        "attrColumns": "ads.file_number as file_number, t.operation ",
        "geomColumn": "shape",
    }

    tbl = params.copy()
    tbl["env"] = envelope_to_bounds_sql(env)

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


def ads_tiles_sql(tile):
    env = tile_to_envelope(tile)
    sql = envelope_to_ads_sql(env)

    return sql
