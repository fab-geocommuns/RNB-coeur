from django.db import migrations

# Renames batid_address.id to batid_address.cle_interop.
#
# The column holds the BAN "clé d'interopérabilité" and, until the primary key
# moves to internal_id, is still the primary key. Naming it "id" is misleading
# now that the building <> address link goes through internal_id; and Django
# forbids a non-primary-key field named "id" (models.E004), so the rename has to
# happen before the primary key switch.
#
# The public contract does not change: the API keeps exposing the key as "id"
# and the data.gouv export keeps its "cle_interop_ban" column.
#
# Anything written outside of this repository that reads batid_address.id (saved
# Metabase questions, SQL scripts) fails with 'column "id" does not exist' from
# now on, rather than silently returning something else. That is intended.
#
# RENAME COLUMN is catalog-only but takes ACCESS EXCLUSIVE on batid_address.
# lock_timeout makes the migration fail fast and roll back, instead of queueing
# every query behind a lock wait.
#
# PL/pgSQL function bodies are not rewritten by PostgreSQL when a column is
# renamed. check_address_is_linked() reads OLD.id: it is replaced in the same
# migration, hence the same transaction, as the rename.


def check_address_is_linked_sql(address_key: str) -> str:
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
                    WHERE addresses_internal_id @> ARRAY[OLD.internal_id]
                ) THEN
                    RAISE EXCEPTION 'Cannot delete address % because it is referenced by a building', OLD.{address_key};
                END IF;

                -- Block deletion if the address is referenced in building history
                IF EXISTS (
                    SELECT 1 FROM batid_building_history
                    WHERE addresses_internal_id @> ARRAY[OLD.internal_id]
                ) THEN
                    RAISE EXCEPTION 'Cannot delete address % because it is referenced in building history', OLD.{address_key};
                END IF;
            END IF;

            RETURN OLD;
        END;
        $function$
        ;
    """  # nosec B608: address_key is a hardcoded literal passed below, not user input


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0153_drop_addresses_id"),
    ]

    operations = [
        migrations.RunSQL(
            "SET lock_timeout = '5s';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            check_address_is_linked_sql("cle_interop"),
            reverse_sql=check_address_is_linked_sql("id"),
        ),
        migrations.RenameField(
            model_name="address",
            old_name="id",
            new_name="cle_interop",
        ),
    ]
