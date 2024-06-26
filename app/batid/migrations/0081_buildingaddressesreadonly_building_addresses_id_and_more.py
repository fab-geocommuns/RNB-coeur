# Generated by Django 4.1.13 on 2024-05-03 14:41
import django.contrib.postgres.fields
import django.contrib.postgres.indexes
import django.db.models.deletion
from django.db import migrations
from django.db import models

from batid.migrations.utils.create_view import sql_migration_building_with_history


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0080_alter_buildingads_unique_together"),
    ]

    operations = [
        migrations.CreateModel(
            name="BuildingAddressesReadOnly",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="building",
            name="addresses_id",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=40), null=True, size=None
            ),
        ),
        migrations.AddField(
            model_name="buildinghistoryonly",
            name="addresses_id",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=40), null=True, size=None
            ),
        ),
        migrations.AddIndex(
            model_name="building",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["addresses_id"], name="bdg_addresses_id_idx"
            ),
        ),
        migrations.AddField(
            model_name="buildingaddressesreadonly",
            name="address",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="batid.address"
            ),
        ),
        migrations.AddField(
            model_name="buildingaddressesreadonly",
            name="building",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="batid.building"
            ),
        ),
        migrations.AddField(
            model_name="building",
            name="addresses_read_only",
            field=models.ManyToManyField(
                blank=True,
                related_name="buildings_read_only",
                through="batid.BuildingAddressesReadOnly",
                to="batid.address",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="buildingaddressesreadonly",
            unique_together={("building", "address")},
        ),
        sql_migration_building_with_history(),
        migrations.RunSQL(
            """
            CREATE OR REPLACE FUNCTION public.keep_building_address_link_updated()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $function$
            DECLARE
                address_id VARCHAR;
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    -- Loop through each address id in the addresses_id array

                    iF (NEW.addresses_id IS NOT NULL) THEN
                        FOREACH address_id IN ARRAY NEW.addresses_id
                        LOOP
                            -- Insert a row into table2 for each address id
                            INSERT INTO batid_buildingaddressesreadonly (building_id, address_id) VALUES (NEW.id, address_id);
                        END LOOP;
                    END IF;
                END IF;

                IF TG_OP = 'UPDATE' THEN
                    -- Check if the addresses_id column's content has changed
                    IF NEW.addresses_id IS DISTINCT FROM  OLD.addresses_id THEN
                        -- Delete existing rows related to the updated row in join table
                        DELETE FROM batid_buildingaddressesreadonly WHERE building_id = NEW.id;

                        -- Loop through each address id in the addresses_id array
                        iF (NEW.addresses_id IS NOT NULL) THEN
                            FOREACH address_id IN ARRAY NEW.addresses_id
                            LOOP
                                -- Insert a row into join table for each address id
                                INSERT INTO batid_buildingaddressesreadonly (building_id, address_id) VALUES (NEW.id, address_id);
                            END LOOP;
                        END IF;
                    END IF;
                END IF;

                IF TG_OP = 'DELETE' THEN
                    delete from batid_buildingaddressesreadonly where building_id = old.id;
                END IF;

                RETURN NEW;
            END;
            $function$
            ;

            create trigger building_addresses_trigger AFTER insert or update or delete on public.batid_building for each row execute function keep_building_address_link_updated();

            CREATE OR REPLACE FUNCTION public.delete_address_id_from_building()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $function$
            DECLARE
                address_id VARCHAR;
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    -- remove the address_id from the addresses_id array
                    UPDATE batid_building SET addresses_id = array_remove(addresses_id, OLD.id) WHERE addresses_id @> ARRAY[OLD.id];
                END IF;

                RETURN NEW;
            END;
            $function$
            ;

            CREATE TRIGGER delete_address_id_from_building_trigger AFTER DELETE ON batid_address FOR EACH ROW EXECUTE FUNCTION delete_address_id_from_building();
            """,
            reverse_sql="""
            DROP TRIGGER building_addresses_trigger ON batid_building;
            DROP FUNCTION keep_building_address_link_updated();
            DROP TRIGGER delete_address_id_from_building_trigger ON batid_address;
            DROP FUNCTION delete_address_id_from_building();
            """,
        ),
    ]
