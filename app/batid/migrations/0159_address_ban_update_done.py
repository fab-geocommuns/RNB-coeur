from django.db import migrations, models

# ban_update_done: has the address been handled by the BAN update? Nullable
# without default, so adding the column only touches the catalog (no table
# rewrite).
#
# Partial index on the addresses still to be handled (ban_update_done null or
# false). The column starts null everywhere, so the index initially holds every
# row of batid_address and its build takes as long as a full index build.
#
# CONCURRENTLY, as in 0158: writes on batid_address are not blocked during the
# build. IF NOT EXISTS: migrate runs in the entrypoint of the web container (the
# API is down until it ends). The column and the index can therefore be created
# by hand in production beforehand, with the exact same statements, and this
# migration then only records them.
#
# A failed CREATE INDEX CONCURRENTLY leaves an INVALID index behind, which IF NOT
# EXISTS would silently accept: the last operation refuses to go on in that case.

INDEX_NAME = "address_ban_update_todo_idx"


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("batid", "0158_address_cle_interop_upper_index"),
    ]

    operations = [
        migrations.RunSQL(
            "SET statement_timeout = '0';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE batid_address "
                    "ADD COLUMN IF NOT EXISTS ban_update_done boolean NULL;",
                    reverse_sql="ALTER TABLE batid_address "
                    "DROP COLUMN IF EXISTS ban_update_done;",
                ),
                migrations.RunSQL(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                    "ON batid_address (internal_id) "
                    "WHERE (ban_update_done IS NULL OR NOT ban_update_done);",
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="address",
                    name="ban_update_done",
                    field=models.BooleanField(default=None, null=True),
                ),
                migrations.AddIndex(
                    model_name="address",
                    index=models.Index(
                        condition=models.Q(
                            ("ban_update_done__isnull", True),
                            ("ban_update_done", False),
                            _connector="OR",
                        ),
                        fields=["internal_id"],
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
