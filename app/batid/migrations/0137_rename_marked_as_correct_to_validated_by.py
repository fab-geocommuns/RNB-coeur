from django.conf import settings
from django.db import migrations, models

from batid.migrations.utils.create_view import sql_migration_building_with_history


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0136_prevent_building_deletion"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name="building",
            old_name="marked_as_correct_by",
            new_name="validated_by",
        ),
        migrations.RenameField(
            model_name="buildinghistoryonly",
            old_name="marked_as_correct_by",
            new_name="validated_by",
        ),
        migrations.RenameModel(
            old_name="BuildingMarkedAsCorrectByReadOnly",
            new_name="BuildingValidatedByReadOnly",
        ),
        migrations.RenameField(
            model_name="building",
            old_name="marked_as_correct_read_only",
            new_name="validated_by_read_only",
        ),
        migrations.AlterField(
            model_name="building",
            name="validated_by_read_only",
            field=models.ManyToManyField(
                blank=True,
                related_name="buildings_validated_by_read_only",
                through="batid.BuildingValidatedByReadOnly",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunSQL(
            sql=[
                "DROP TRIGGER IF EXISTS building_marked_as_correct_by_trigger ON batid_building;",
                "DROP FUNCTION IF EXISTS keep_building_marked_as_correct_by_updated();",
                """
                CREATE OR REPLACE FUNCTION public.keep_building_validated_by_updated()
                RETURNS trigger AS $$
                DECLARE
                    user_id INTEGER;
                BEGIN
                    IF TG_OP = 'INSERT' THEN
                        IF (NEW.validated_by IS NOT NULL) THEN
                            FOREACH user_id IN ARRAY NEW.validated_by
                            LOOP
                                INSERT INTO batid_buildingvalidatedbyreadonly (building_id, user_id)
                                VALUES (NEW.id, user_id);
                            END LOOP;
                        END IF;
                    ELSIF TG_OP = 'UPDATE' THEN
                        IF NEW.validated_by IS DISTINCT FROM OLD.validated_by THEN
                            DELETE FROM batid_buildingvalidatedbyreadonly WHERE building_id = NEW.id;
                            IF (NEW.validated_by IS NOT NULL) THEN
                                FOREACH user_id IN ARRAY NEW.validated_by
                                LOOP
                                    INSERT INTO batid_buildingvalidatedbyreadonly (building_id, user_id)
                                    VALUES (NEW.id, user_id);
                                END LOOP;
                            END IF;
                        END IF;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """,
                "CREATE TRIGGER building_validated_by_trigger AFTER INSERT OR UPDATE ON public.batid_building FOR EACH ROW EXECUTE FUNCTION keep_building_validated_by_updated();",
            ],
            reverse_sql=[
                "DROP TRIGGER IF EXISTS building_validated_by_trigger ON batid_building;",
                "DROP FUNCTION IF EXISTS keep_building_validated_by_updated();",
                """
                CREATE OR REPLACE FUNCTION public.keep_building_marked_as_correct_by_updated()
                RETURNS trigger AS $$
                DECLARE
                    user_id INTEGER;
                BEGIN
                    IF TG_OP = 'INSERT' THEN
                        IF (NEW.marked_as_correct_by IS NOT NULL) THEN
                            FOREACH user_id IN ARRAY NEW.marked_as_correct_by
                            LOOP
                                INSERT INTO batid_buildingmarkedascorrectbyreadonly (building_id, user_id)
                                VALUES (NEW.id, user_id);
                            END LOOP;
                        END IF;
                    ELSIF TG_OP = 'UPDATE' THEN
                        IF NEW.marked_as_correct_by IS DISTINCT FROM OLD.marked_as_correct_by THEN
                            DELETE FROM batid_buildingmarkedascorrectbyreadonly WHERE building_id = NEW.id;
                            IF (NEW.marked_as_correct_by IS NOT NULL) THEN
                                FOREACH user_id IN ARRAY NEW.marked_as_correct_by
                                LOOP
                                    INSERT INTO batid_buildingmarkedascorrectbyreadonly (building_id, user_id)
                                    VALUES (NEW.id, user_id);
                                END LOOP;
                            END IF;
                        END IF;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """,
                "CREATE TRIGGER building_marked_as_correct_by_trigger AFTER INSERT OR UPDATE ON public.batid_building FOR EACH ROW EXECUTE FUNCTION keep_building_marked_as_correct_by_updated();",
            ],
        ),
        sql_migration_building_with_history(),
    ]
