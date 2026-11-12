from django.db import migrations

# Drops the GIST indexes on geography(shape) created by hand in 0073 (8.5 GB on
# batid_building, 14 GB on batid_plot). Since #1173, every distance query
# pre-filters with `shape && ST_Expand(...)`, served by the geometry indexes.
#
# Must only be deployed once that pre-filter runs in production: older code
# without these indexes does full scans of batid_building and batid_plot.
#
# CONCURRENTLY: the API is not blocked, but each DROP waits for the end of every
# open transaction on the table. lock_timeout bounds each wait (5 s, as in 0148):
# if it fires, the deploy stops before the rollout, the previous version keeps
# running, and the migration is replayed later. IF EXISTS makes the replay drop an
# index left INVALID by an interrupted DROP.
#
# Reverse is a noop: recreating 22.5 GB takes hours and must stay a deliberate
# by-hand operation, at a quiet time:
#   CREATE INDEX CONCURRENTLY IF NOT EXISTS batid_building_shape_geog ON batid_building USING GIST (geography(shape));
#   CREATE INDEX CONCURRENTLY IF NOT EXISTS batid_plot_shape_geog ON batid_plot USING GIST (geography(shape));
# then check pg_index.indisvalid for both.


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("batid", "0161_emailnotificationoptout"),
    ]

    operations = [
        migrations.RunSQL(
            "SET statement_timeout = '0';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "SET lock_timeout = '5s';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "DROP INDEX CONCURRENTLY IF EXISTS batid_building_shape_geog;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "DROP INDEX CONCURRENTLY IF EXISTS batid_plot_shape_geog;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
