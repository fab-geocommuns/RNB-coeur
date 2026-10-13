from django.db import migrations, models

# Index on ban_update_done (column added in 0159). It holds every row of
# batid_address, so its build reads and sorts the whole table.
#
# CONCURRENTLY, as in 0158: writes on batid_address are not blocked during the
# build. IF NOT EXISTS: migrate runs in the entrypoint of the web container (the
# API is down until it ends). The index can therefore be built by hand in
# production beforehand, with the exact same statement, and this migration then
# only records it.
#
# A failed CREATE INDEX CONCURRENTLY leaves an INVALID index behind, which IF NOT
# EXISTS would silently accept: the last operation refuses to go on in that case.

INDEX_NAME = "address_ban_update_done_idx"


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("batid", "0159_address_ban_update_done"),
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
                    "ON batid_address (ban_update_done);",
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="address",
                    index=models.Index(
                        fields=["ban_update_done"],
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
