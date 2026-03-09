import importlib

from django.db import migrations

_migration0081 = importlib.import_module(
    "batid.migrations.0081_buildingaddressesreadonly_building_addresses_id_and_more"
)
DELETE_ADDRESS_ID_FROM_BUILDING_TRIGGER_SQL = (
    _migration0081.DELETE_ADDRESS_ID_FROM_BUILDING_TRIGGER_SQL
)


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0124_remove_unused_building_statuses"),
    ]

    operations = [
        migrations.RunSQL(
            """
            -- Drop the old trigger and function
            DROP TRIGGER IF EXISTS delete_address_id_from_building_trigger ON batid_address;
            DROP FUNCTION IF EXISTS public.delete_address_id_from_building();

            -- Create the new function and trigger
            CREATE OR REPLACE FUNCTION public.check_address_is_linked()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $function$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    -- Block deletion if the address is referenced in any current building
                    IF EXISTS (
                        SELECT 1 FROM batid_building
                        WHERE addresses_id @> ARRAY[OLD.id]
                    ) THEN
                        RAISE EXCEPTION 'Cannot delete address % because it is referenced by a building', OLD.id;
                    END IF;

                    -- Block deletion if the address is referenced in building history
                    IF EXISTS (
                        SELECT 1 FROM batid_building_history
                        WHERE addresses_id @> ARRAY[OLD.id]
                    ) THEN
                        RAISE EXCEPTION 'Cannot delete address % because it is referenced in building history', OLD.id;
                    END IF;
                END IF;

                RETURN OLD;
            END;
            $function$
            ;

            CREATE TRIGGER prevent_delete_linked_address_trigger BEFORE DELETE ON batid_address FOR EACH ROW EXECUTE FUNCTION check_address_is_linked();
            """,
            reverse_sql=f"""
            -- Drop the new trigger and function
            DROP TRIGGER IF EXISTS prevent_delete_linked_address_trigger ON batid_address;
            DROP FUNCTION IF EXISTS public.check_address_is_linked();

            -- Recreate the old trigger and function

            """ + DELETE_ADDRESS_ID_FROM_BUILDING_TRIGGER_SQL,  # nosec
        ),
    ]
