from batid.models import Building
from batid.services.vector_tiles.common import envelope_to_bounds_sql
from batid.services.vector_tiles.common import Envelope, TileParams, tile_to_envelope
from batid.services.bdg_status import BuildingStatus


def get_real_buildings_status():
    return ", ".join(
        ["'" + status + "'" for status in BuildingStatus.REAL_BUILDINGS_STATUS]
    )


def envelope_to_buildings_sql(
    env: Envelope, geometry_column: str, only_active_and_real: bool = True
) -> str:
    params = {
        "table": Building._meta.db_table,
        "srid": str(4326),
        "attrColumns": "rnb_id",
    }
    params["geomColumn"] = geometry_column

    tbl = params.copy()
    tbl["env"] = envelope_to_bounds_sql(env)
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


def bdgs_tiles_sql(tile: TileParams, data_type: str, only_active_and_real: bool) -> str:
    env = tile_to_envelope(tile)
    if data_type == "shape":
        geometry_column = "shape"
    elif data_type == "point":
        geometry_column = "point"
    sql = envelope_to_buildings_sql(env, geometry_column, only_active_and_real)

    return sql
