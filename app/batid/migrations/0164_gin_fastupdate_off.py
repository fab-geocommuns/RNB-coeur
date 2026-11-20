import django.contrib.postgres.indexes
from django.db import migrations

# Switches the 7 GIN indexes of the buildings and their history to
# fastupdate = off (#1204). With fastupdate on, a single-row UPDATE sometimes
# flushes a full GIN pending list into the index and runs past the web
# statement_timeout. Which index flushes is unknown, so all 7 are switched.
#
# Hand-written: the generated migration would drop and recreate each index
# without CONCURRENTLY (15 GB for bdg_ext_ids_idx) in one transaction, locking
# each table, reads included, until the rebuild ends.
#
# Each ALTER INDEX takes an ACCESS EXCLUSIVE lock on its index, and every query
# on the table, reads included, queues behind an ALTER waiting for it. Non-atomic,
# so only one index is locked at a time and each lock is released at once.
# lock_timeout bounds each wait (5 s): if it fires, the deploy stops before the
# rollout, the previous version keeps running, and the migration is replayed
# later. An index already switched stays off, which is harmless.
#
# ALTER INDEX does not flush the pending lists already filled, so the migration
# then empties them with gin_clean_pending_list, which does not block writes.
# The app statement_timeout, which migrate runs with, would cut the cleaning of
# bdg_ext_ids_idx (57 s on staging): it is lifted for the cleaning only.

GIN_INDEXES = [
    # (model_name, index name, fields as declared in the model)
    ("building", "bdg_ext_ids_idx", ["ext_ids"]),
    ("buildinghistoryonly", "bdg_history_event_origin_idx", ["event_origin"]),
    ("buildinghistoryonly", "bdg_hist_addr_internal_id_idx", ["addresses_internal_id"]),
    ("buildinghistoryonly", "bdg_hist_parent_buildings_idx", ["parent_buildings"]),
    ("building", "bdg_event_origin_idx", ["event_origin"]),
    ("building", "bdg_addresses_internal_id_idx", ["addresses_internal_id"]),
    ("building", "bdg_parent_buildings_idx", ["parent_buildings"]),
]


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("batid", "0163_drop_unused_apirequestlog_indexes"),
    ]

    operations = [
        migrations.RunSQL(
            "SET lock_timeout = '5s';",
            reverse_sql="RESET lock_timeout;",
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    f"ALTER INDEX {name} SET (fastupdate = off);",
                    reverse_sql=f"ALTER INDEX {name} RESET (fastupdate);",
                )
                for _, name, _ in GIN_INDEXES
            ],
            state_operations=[
                operation
                for model_name, name, fields in GIN_INDEXES
                for operation in (
                    migrations.RemoveIndex(model_name=model_name, name=name),
                    migrations.AddIndex(
                        model_name=model_name,
                        index=django.contrib.postgres.indexes.GinIndex(
                            fields=fields, name=name, fastupdate=False
                        ),
                    ),
                )
            ],
        ),
        # The SET above lasts for the whole connection: the migrations applied
        # after this one in the same migrate must get the default lock_timeout back.
        migrations.RunSQL(
            "RESET lock_timeout;",
            reverse_sql="SET lock_timeout = '5s';",
        ),
        migrations.RunSQL(
            [
                "SET statement_timeout = 0;",
                *(
                    f"SELECT gin_clean_pending_list('{name}'::regclass);"
                    for _, name, _ in GIN_INDEXES
                ),
                "RESET statement_timeout;",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
