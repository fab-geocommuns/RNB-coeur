from django.db import migrations

# check_address_is_linked() (prevent_delete_linked_address_trigger, see 0125) now
# looks for the address in addresses_internal_id instead of addresses_id, using
# the GIN indexes added in 0151.
# The trigger itself is bound to the function by name: replacing the function is
# enough. Error messages still show OLD.id, the BAN "clé d'interopérabilité".


def check_address_is_linked_sql(column: str, value: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION public.check_address_is_linked()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                -- Block deletion if the address is referenced in any current building
                IF EXISTS (
                    SELECT 1 FROM batid_building
                    WHERE {column} @> ARRAY[{value}]
                ) THEN
                    RAISE EXCEPTION 'Cannot delete address % because it is referenced by a building', OLD.id;
                END IF;

                -- Block deletion if the address is referenced in building history
                IF EXISTS (
                    SELECT 1 FROM batid_building_history
                    WHERE {column} @> ARRAY[{value}]
                ) THEN
                    RAISE EXCEPTION 'Cannot delete address % because it is referenced in building history', OLD.id;
                END IF;
            END IF;

            RETURN OLD;
        END;
        $function$
        ;
    """  # nosec B608: column/value are hardcoded literals passed below, not user input


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0151_gin_index_addresses_internal_id"),
    ]

    operations = [
        migrations.RunSQL(
            check_address_is_linked_sql("addresses_internal_id", "OLD.internal_id"),
            reverse_sql=check_address_is_linked_sql("addresses_id", "OLD.id"),
        ),
    ]
