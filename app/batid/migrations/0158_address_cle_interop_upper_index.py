import django.contrib.postgres.indexes
import django.db.models.functions.text
from django.db import migrations, models

# Index on UPPER(cle_interop), for case-insensitive lookups on the BAN "clé
# d'interopérabilité": some keys in db are uppercase ("2A004_...") while the BAN
# files hold lowercase ones. text_pattern_ops serves both the equality (IN) and
# the prefix (istartswith) lookups.
#
# CONCURRENTLY, as in 0151: writes on batid_address are not blocked during the
# build. IF NOT EXISTS: the table holds one row per address of France and migrate
# runs in the entrypoint of the web container (the API is down until it ends).
# The index can therefore be built by hand in production beforehand, with the
# exact same statement, and this migration then only records it.
#
# A failed CREATE INDEX CONCURRENTLY leaves an INVALID index behind, which IF NOT
# EXISTS would silently accept: the last operation refuses to go on in that case.

INDEX_NAME = "address_cle_interop_upper_idx"


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("batid", "0157_city_has_reliable_ban_ids"),
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
                    "ON batid_address (upper(cle_interop) text_pattern_ops);",
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="address",
                    index=models.Index(
                        django.contrib.postgres.indexes.OpClass(
                            django.db.models.functions.text.Upper("cle_interop"),
                            name="text_pattern_ops",
                        ),
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
