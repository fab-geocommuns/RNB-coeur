# Drops batid_building.addresses_id and batid_building_history.addresses_id, the
# BAN "clé d'interopérabilité" array that addresses_internal_id replaces as the
# building <> address link, together with everything that only existed for it:
# the old join table batid_buildingaddressesreadonly and its two GIN indexes.
#
# The order of the operations matters:
# - keep_building_address_link_updated() still reads NEW.addresses_id. PL/pgSQL
#   does not check column names when the function is created, so it has to be
#   replaced before the column goes away, or the first write on batid_building
#   would fail at runtime ("record new has no field addresses_id");
# - batid_building_with_history is a "SELECT *" frozen at creation, which
#   blocks any DROP COLUMN as long as it exists: it is dropped first and
#   recreated at the end.
#
# Irreversible on purpose: the BAN keys of a row can still be recomputed from
# addresses_internal_id through batid_address (internal_id -> id).
#
# Like 0149, ACCESS EXCLUSIVE is taken on batid_building and
# batid_building_history. lock_timeout makes the migration fail fast and roll
# back, instead of queueing every query behind a lock wait.

from batid.migrations.utils.create_view import (
    sql_migration_building_with_history_create_view,
    sql_migration_building_with_history_drop_view,
)
from django.db import migrations

KEEP_BUILDING_ADDRESS_LINK_UPDATED_SQL = """
            CREATE OR REPLACE FUNCTION public.keep_building_address_link_updated()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $function$
            DECLARE
                address_internal_id BIGINT;
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    iF (NEW.addresses_internal_id IS NOT NULL) THEN
                        FOREACH address_internal_id IN ARRAY NEW.addresses_internal_id
                        LOOP
                            INSERT INTO batid_buildingaddressesinternalidreadonly (building_id, address_id) VALUES (NEW.id, address_internal_id);
                        END LOOP;
                    END IF;
                END IF;

                IF TG_OP = 'UPDATE' THEN
                    IF NEW.addresses_internal_id IS DISTINCT FROM OLD.addresses_internal_id THEN
                        DELETE FROM batid_buildingaddressesinternalidreadonly WHERE building_id = NEW.id;

                        iF (NEW.addresses_internal_id IS NOT NULL) THEN
                            FOREACH address_internal_id IN ARRAY NEW.addresses_internal_id
                            LOOP
                                INSERT INTO batid_buildingaddressesinternalidreadonly (building_id, address_id) VALUES (NEW.id, address_internal_id);
                            END LOOP;
                        END IF;
                    END IF;
                END IF;

                IF TG_OP = 'DELETE' THEN
                    delete from batid_buildingaddressesinternalidreadonly where building_id = old.id;
                END IF;

                RETURN NEW;
            END;
            $function$
            ;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0152_check_address_is_linked_internal_id"),
    ]

    operations = [
        migrations.RunSQL(
            "SET statement_timeout = '0'; SET lock_timeout = '5s';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # No reverse_sql: this is the operation that makes the migration
        # irreversible.
        migrations.RunSQL(KEEP_BUILDING_ADDRESS_LINK_UPDATED_SQL),
        sql_migration_building_with_history_drop_view(),
        # The M2M goes first, so that deleting its through model is a plain
        # DROP TABLE.
        migrations.RemoveField(
            model_name="building",
            name="addresses_read_only",
        ),
        migrations.DeleteModel(
            name="BuildingAddressesReadOnly",
        ),
        migrations.RemoveIndex(
            model_name="building",
            name="bdg_addresses_id_idx",
        ),
        migrations.RemoveIndex(
            model_name="buildinghistoryonly",
            name="bdg_history_addresses_id_idx",
        ),
        migrations.RemoveField(
            model_name="building",
            name="addresses_id",
        ),
        migrations.RemoveField(
            model_name="buildinghistoryonly",
            name="addresses_id",
        ),
        sql_migration_building_with_history_create_view(),
    ]
