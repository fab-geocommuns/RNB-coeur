from django.db import migrations

# Drops 7 indexes of the API request log, unused since at least 22/10/2026
# (pg_stat_statements, pg_stat_user_indexes on prod): 14.4 GB, 11 GB of them for
# view_view_method_at. Every insert of a logged API call kept updating them.
#
# The two composite ones were created by hand on prod, staging and sandbox, with
# no migration: they do not exist on a fresh DB, hence IF EXISTS. The other five
# come from the drf-api-tracking migrations, hence the dependency on its last one.
#
# CONCURRENTLY: logging is not blocked, but each DROP waits for the end of every
# open transaction on the table. lock_timeout bounds each wait (5 s, as in 0148):
# if it fires, the deploy stops before the rollout, the previous version keeps
# running, and the migration is replayed later. IF EXISTS also makes the replay
# drop an index left INVALID by an interrupted DROP.
#
# The library model keeps db_index=True on view, view_method and status_code: a
# library migration altering view or view_method to a non-varchar type would
# recreate their _like index, without CONCURRENTLY. Check its migrations on every
# drf-api-tracking upgrade.
#
# Reverse is a noop: recreating 14.4 GB on a 100 GB table takes hours and must stay
# a deliberate by-hand operation, at a quiet time:
#   CREATE INDEX CONCURRENTLY IF NOT EXISTS rest_framework_tracking_apirequestlog_status_code_3c9e2003 ON rest_framework_tracking_apirequestlog (status_code);
#   CREATE INDEX CONCURRENTLY IF NOT EXISTS rest_framework_tracking_apirequestlog_view_5bd1e407 ON rest_framework_tracking_apirequestlog (view);
#   CREATE INDEX CONCURRENTLY IF NOT EXISTS rest_framework_tracking_apirequestlog_view_5bd1e407_like ON rest_framework_tracking_apirequestlog (view varchar_pattern_ops);
#   CREATE INDEX CONCURRENTLY IF NOT EXISTS rest_framework_tracking_apirequestlog_view_method_dd790881 ON rest_framework_tracking_apirequestlog (view_method);
#   CREATE INDEX CONCURRENTLY IF NOT EXISTS rest_framework_tracking_apirequestlog_view_method_dd790881_like ON rest_framework_tracking_apirequestlog (view_method varchar_pattern_ops);
#   CREATE INDEX CONCURRENTLY IF NOT EXISTS rest_framework_tracking_apirequestlog_view_view_method ON rest_framework_tracking_apirequestlog (view, view_method);
#   CREATE INDEX CONCURRENTLY IF NOT EXISTS rest_framework_tracking_apirequestlog_view_view_method_at ON rest_framework_tracking_apirequestlog (view, view_method, requested_at);
# then check pg_index.indisvalid for each. IF NOT EXISTS skips an INVALID index
# (left by an interrupted DROP or CREATE): drop it with DROP INDEX CONCURRENTLY,
# then run its CREATE again.

DROPPED_INDEXES = [
    "rest_framework_tracking_apirequestlog_status_code_3c9e2003",
    "rest_framework_tracking_apirequestlog_view_5bd1e407",
    "rest_framework_tracking_apirequestlog_view_5bd1e407_like",
    "rest_framework_tracking_apirequestlog_view_method_dd790881",
    "rest_framework_tracking_apirequestlog_view_method_dd790881_like",
    "rest_framework_tracking_apirequestlog_view_view_method",
    "rest_framework_tracking_apirequestlog_view_view_method_at",
]


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("batid", "0162_drop_shape_geography_indexes"),
        ("rest_framework_tracking", "0013_apirequestlog_user_agent"),
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
        *[
            migrations.RunSQL(
                f"DROP INDEX CONCURRENTLY IF EXISTS {name};",
                reverse_sql=migrations.RunSQL.noop,
            )
            for name in DROPPED_INDEXES
        ],
        # The SETs above last for the whole connection: the migrations applied
        # after this one in the same migrate must get the app timeouts back.
        migrations.RunSQL(
            "RESET statement_timeout; RESET lock_timeout;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
