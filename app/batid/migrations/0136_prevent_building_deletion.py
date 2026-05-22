from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0135_alter_organization_managed_cities_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            """
            CREATE OR REPLACE FUNCTION public.prevent_building_deletion()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $function$
            BEGIN
                RAISE EXCEPTION 'Cannot delete row from %: deletions are forbidden to preserve RNB history. Use Building.deactivate() instead.', TG_TABLE_NAME;
            END;
            $function$
            ;

            CREATE TRIGGER prevent_delete_building_trigger BEFORE DELETE ON batid_building FOR EACH ROW EXECUTE FUNCTION prevent_building_deletion();
            CREATE TRIGGER prevent_delete_building_history_trigger BEFORE DELETE ON batid_building_history FOR EACH ROW EXECUTE FUNCTION prevent_building_deletion();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS prevent_delete_building_history_trigger ON batid_building_history;
            DROP TRIGGER IF EXISTS prevent_delete_building_trigger ON batid_building;
            DROP FUNCTION IF EXISTS public.prevent_building_deletion();
            """,
        ),
    ]
