from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0120_address_ban_id"),
    ]

    operations = [
        migrations.RunSQL(
            """
            CREATE OR REPLACE FUNCTION public.delete_address_id_from_building()
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
            """,
            reverse_sql="""
            CREATE OR REPLACE FUNCTION public.delete_address_id_from_building()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $function$
            DECLARE
                address_id VARCHAR;
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    UPDATE batid_building SET addresses_id = array_remove(addresses_id, OLD.id) WHERE addresses_id @> ARRAY[OLD.id];
                END IF;

                RETURN NEW;
            END;
            $function$
            ;
            """,
        ),
    ]
