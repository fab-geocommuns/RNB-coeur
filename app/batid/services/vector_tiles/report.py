from batid.services.vector_tiles.common import Envelope
from batid.services.vector_tiles.common import envelope_to_bounds_sql
from batid.services.vector_tiles.common import tile_to_envelope
from batid.services.vector_tiles.common import TileParams


def envelope_to_report_sql(env: Envelope) -> str:

    params = {
        "env": envelope_to_bounds_sql(env),
    }

    sql_tmpl = """
            WITH
            bounds AS (
                SELECT {env} AS geom,
                       {env}::box2d AS b2d
            ),
            mvtgeom AS (
                SELECT ST_AsMVTGeom(ST_Transform(report.point, 3857), bounds.b2d) AS geom,
                       report.id, report.status, ARRAY_AGG(tag.id) AS tag_ids
                FROM bounds, batid_report AS report
                LEFT JOIN taggit_taggeditem AS tagged_item
                    ON tagged_item.object_id = report.id
                LEFT JOIN django_content_type
                    ON tagged_item.content_type_id = django_content_type.id
                    AND django_content_type.model = 'report'
                    AND django_content_type.app_label = 'batid'
                LEFT JOIN taggit_tag AS tag
                    ON tagged_item.tag_id = tag.id
                WHERE ST_Intersects(report.point, ST_Transform(bounds.geom, 4326))
                GROUP BY ST_AsMVTGeom(ST_Transform(report.point, 3857), bounds.b2d),
                       report.id, report.status
            )
            SELECT ST_AsMVT(mvtgeom.*) FROM mvtgeom
        """
    return sql_tmpl.format(**params)


def reports_tiles_sql(tile: TileParams) -> str:
    env = tile_to_envelope(tile)
    sql = envelope_to_report_sql(env)
    return sql
