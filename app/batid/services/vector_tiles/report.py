from batid.models import Report
from batid.services.vector_tiles.common import tile_to_envelope
from batid.services.vector_tiles.common import envelope_to_bounds_sql
from batid.services.vector_tiles.common import TileParams
from batid.services.vector_tiles.common import Envelope


def envelope_to_report_sql(env: Envelope) -> str:

    params = {
        "table": Report._meta.db_table,
        "srid": str(4326),
        "attrColumns": "id, status",
        "geomColumn": "point",
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
                FROM {table} t, bounds
                WHERE ST_Intersects(t.{geomColumn}, ST_Transform(bounds.geom, {srid}))
            )
            SELECT ST_AsMVT(mvtgeom.*) FROM mvtgeom
        """
    return sql_tmpl.format(**tbl)


def reports_tiles_sql(tile: TileParams) -> str:
    env = tile_to_envelope(tile)
    sql = envelope_to_report_sql(env)
    return sql
