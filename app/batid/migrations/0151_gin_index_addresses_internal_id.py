import django.contrib.postgres.indexes
from django.db import migrations

# GIN indexes on addresses_internal_id, needed before switching the "@>" reads of
# addresses_id (address deletion, check_address_is_linked() trigger) to it. See
# specs/migration_lien_batiment_adresse.md.
#
# CONCURRENTLY, as in 0107: writes on the buildings are not blocked during the
# build. IF NOT EXISTS: the index on batid_building_history is long to build, and
# migrate runs in the entrypoint of the web container (the API is down until it
# ends). The indexes can therefore be built by hand in production beforehand,
# with the exact same statements, and this migration then only records them.
#
# A failed CREATE INDEX CONCURRENTLY leaves an INVALID index behind, which IF NOT
# EXISTS would silently accept: the last operation refuses to go on in that case.

INDEXES = [
    ("bdg_addresses_internal_id_idx", "batid_building"),
    ("bdg_hist_addr_internal_id_idx", "batid_building_history"),
]


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("batid", "0150_buildingaddressesinternalidreadonly"),
    ]

    operations = [
        migrations.RunSQL(
            "SET statement_timeout = '0';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                    f"ON {table} USING gin (addresses_internal_id);",
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {name};",
                )
                for name, table in INDEXES
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="building",
                    index=django.contrib.postgres.indexes.GinIndex(
                        fields=["addresses_internal_id"],
                        name="bdg_addresses_internal_id_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="buildinghistoryonly",
                    index=django.contrib.postgres.indexes.GinIndex(
                        fields=["addresses_internal_id"],
                        name="bdg_hist_addr_internal_id_idx",
                    ),
                ),
            ],
        ),
        migrations.RunSQL(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_index i
                    JOIN pg_class c ON c.oid = i.indexrelid
                    WHERE c.relname IN (
                        'bdg_addresses_internal_id_idx',
                        'bdg_hist_addr_internal_id_idx'
                    )
                    AND NOT i.indisvalid
                ) THEN
                    RAISE EXCEPTION 'Index GIN sur addresses_internal_id INVALID : le supprimer (DROP INDEX CONCURRENTLY) puis relancer la migration';
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
