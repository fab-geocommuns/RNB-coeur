from django.db import migrations

# Partial indexes on event_id, restricted to contributions. They make the
# "is this SummerChallenge row a contribution?" lookup of
# batid.services.edition_stats.contributions() cheap: the predicate is implied
# by the index, so the wide building rows no longer need to be read.
#
# The predicate must stay identical to what KT("event_origin__source")
# generates (->>), otherwise the planner does not use these indexes. No state
# operation for the same reason: models.Index(condition=Q(...)) would describe
# a different predicate (->).
#
# CONCURRENTLY, as in 0160: writes on the building tables are not blocked
# during the build. IF NOT EXISTS: the indexes can be built by hand in
# production beforehand, with the exact same statements, and this migration
# then only checks them.
#
# A failed CREATE INDEX CONCURRENTLY leaves an INVALID index behind, which IF
# NOT EXISTS would silently accept: the check after each index refuses to go on
# in that case.

PREDICATE = "(event_origin ->> 'source') = 'contribution'"


def check_valid(name: str) -> migrations.RunSQL:
    return migrations.RunSQL(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = '{name}'
                AND NOT i.indisvalid
            ) THEN
                RAISE EXCEPTION 'Index {name} INVALID : le supprimer (DROP INDEX CONCURRENTLY) puis relancer la migration';
            END IF;
        END $$;
        """,  # nosec B608: name is a hardcoded literal, not user input
        reverse_sql=migrations.RunSQL.noop,
    )


def create_index(name: str, table: str) -> migrations.RunSQL:
    return migrations.RunSQL(
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
        f"ON {table} (event_id) WHERE {PREDICATE};",
        reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {name};",
    )


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
        create_index("bdg_contribution_event_idx", "batid_building"),
        check_valid("bdg_contribution_event_idx"),
        create_index("bdg_history_contribution_event_idx", "batid_building_history"),
        check_valid("bdg_history_contribution_event_idx"),
    ]
