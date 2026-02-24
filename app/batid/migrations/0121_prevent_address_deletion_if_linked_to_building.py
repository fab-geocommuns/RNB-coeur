from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0120_address_ban_id"),
    ]

    operations = [
        migrations.RunSQL(
            """
            -- Disable the old trigger
            ALTER TABLE batid_address DISABLE TRIGGER delete_address_id_from_building_trigger;

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
            reverse_sql="""
            -- Drop the new trigger and function
            DROP TRIGGER IF EXISTS prevent_delete_linked_address_trigger ON batid_address;
            DROP FUNCTION IF EXISTS public.check_address_is_linked();

            -- Re-enable the old trigger
            ALTER TABLE batid_address ENABLE TRIGGER delete_address_id_from_building_trigger;
            """,
        ),
    ]
