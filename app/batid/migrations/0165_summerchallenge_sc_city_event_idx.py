from django.db import migrations, models

# Covering index for the contribution summary (GET /api/alpha/contributions/
# summaries/): it counts the distinct events of each city in one pass, read
# from the index alone. About 60 MB for 1.3 million rows.
#
# CONCURRENTLY: the inserts into batid_summerchallenge (every contribution
# writes some) are not blocked while the index is built. The previous code
# does not use it, so it runs unchanged during the deploy.
#
# IF NOT EXISTS, as in 0160: a migrate interrupted after the build (container
# killed) leaves the index without recording the migration, and the next deploy
# then only records it. The index can also be built by hand in production
# beforehand, with the exact same statement.
#
# A failed CREATE INDEX CONCURRENTLY leaves an INVALID index behind, which IF NOT
# EXISTS would silently accept: the last operation refuses to go on in that case.

INDEX_NAME = "sc_city_event_idx"


class Migration(migrations.Migration):

    atomic = False
    dependencies = [
        ("batid", "0164_gin_fastupdate_off"),
    ]

    operations = [
        migrations.RunSQL(
            "SET statement_timeout = '0';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                    "ON batid_summerchallenge (city_id, event_id) "
                    "INCLUDE (created_at, user_id) WHERE city_id IS NOT NULL;",
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="summerchallenge",
                    index=models.Index(
                        condition=models.Q(("city__isnull", False)),
                        fields=["city", "event_id"],
                        include=("created_at", "user"),
                        name=INDEX_NAME,
                    ),
                ),
            ],
        ),
        migrations.RunSQL(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_index i
                    JOIN pg_class c ON c.oid = i.indexrelid
                    WHERE c.relname = '{INDEX_NAME}'
                    AND NOT i.indisvalid
                ) THEN
                    RAISE EXCEPTION 'Index {INDEX_NAME} INVALID : le supprimer (DROP INDEX CONCURRENTLY) puis relancer la migration';
                END IF;
            END $$;
            """,  # nosec B608: INDEX_NAME is a hardcoded literal, not user input
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
