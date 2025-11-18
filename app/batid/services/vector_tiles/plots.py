from batid.models import Plot
from batid.services.vector_tiles.common import tile_to_envelope
from batid.services.vector_tiles.common import envelope_to_bounds_sql


def envelope_to_plots_sql(env):
    params = {
        "table": Plot._meta.db_table,
        "srid": str(4326),
        "attrColumns": "id, regexp_replace(id, '^.*[A-Za-z]0?', '') AS plot_number ",
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
                    FROM {table} t, bounds
                    WHERE ST_Intersects(t.{geomColumn}, ST_Transform(bounds.geom, {srid}))
                )
                SELECT ST_AsMVT(mvtgeom.*) FROM mvtgeom
            """
    return sql_tmpl.format(**tbl)


def plots_tiles_sql(tile):
    env = tile_to_envelope(tile)
    sql = envelope_to_plots_sql(env)

    return sql
