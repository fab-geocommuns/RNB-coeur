from django.db import migrations

# First step of the switch of the batid_address primary key from cle_interop
# (the BAN "clé d'interopérabilité", varchar) to internal_id (bigint).
#
# cle_interop is looked up everywhere (Address.objects.filter(cle_interop=...),
# the joins of the raw SQL): it has to stay uniquely indexed once it stops being
# the primary key. Dropping the primary key drops its index, so the replacement
# is built first, here, and 0156 only promotes it to a UNIQUE constraint.
#
# CONCURRENTLY, as in 0151: writes on batid_address are not blocked during the
# build. IF NOT EXISTS: the table holds one row per address of France and migrate
# runs in the entrypoint of the web container (the API is down until it ends).
# The index can therefore be built by hand in production beforehand, with the
# exact same statement, and this migration then only records it.
#
# A failed CREATE INDEX CONCURRENTLY leaves an INVALID index behind, which IF NOT
# EXISTS would silently accept: the last operation refuses to go on in that case.
#
# Nothing in the model state: the index only becomes the UNIQUE constraint of the
# cle_interop field in 0156.

INDEX_NAME = "batid_address_cle_interop_uniq"


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("batid", "0154_rename_address_id_to_cle_interop"),
    ]

    operations = [
        migrations.RunSQL(
            "SET statement_timeout = '0';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
            "ON batid_address (cle_interop);",
            reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
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
                    RAISE EXCEPTION 'Index unique {INDEX_NAME} INVALID : le supprimer (DROP INDEX CONCURRENTLY) puis relancer la migration';
                END IF;
            END $$;
            """,  # nosec B608: INDEX_NAME is a hardcoded literal, not user input
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
