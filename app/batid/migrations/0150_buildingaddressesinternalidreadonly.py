# PR 6 of the migration of the building <-> address link towards an internal
# key (see specs/migration_lien_batiment_adresse.md).
#
# New join table, mirroring batid_buildingaddressesreadonly but keyed on
# batid_address.internal_id instead of the BAN interop key. Kept in sync from
# Building.addresses_internal_id by extending keep_building_address_link_updated()
# (created in 0081) to maintain both join tables in the same pass, rather than
# adding a second trigger that would double the DELETE + N INSERT on every write.
#
# Schema and trigger only: addresses_internal_id itself is not backfilled yet
# (see 0148), so this table stays empty for existing buildings until that
# backfill lands — the trigger only takes over future writes from here on.

import django.db.models.deletion
from django.db import migrations, models

OLD_KEEP_BUILDING_ADDRESS_LINK_UPDATED_SQL = """
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
"""

NEW_KEEP_BUILDING_ADDRESS_LINK_UPDATED_SQL = """
            CREATE OR REPLACE FUNCTION public.keep_building_address_link_updated()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $function$
            DECLARE
                address_id VARCHAR;
                address_internal_id BIGINT;
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

                    -- Same, but for addresses_internal_id / batid_buildingaddressesinternalidreadonly
                    iF (NEW.addresses_internal_id IS NOT NULL) THEN
                        FOREACH address_internal_id IN ARRAY NEW.addresses_internal_id
                        LOOP
                            INSERT INTO batid_buildingaddressesinternalidreadonly (building_id, address_id) VALUES (NEW.id, address_internal_id);
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

                    -- Same, but for addresses_internal_id / batid_buildingaddressesinternalidreadonly
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
                    delete from batid_buildingaddressesreadonly where building_id = old.id;
                    delete from batid_buildingaddressesinternalidreadonly where building_id = old.id;
                END IF;

                RETURN NEW;
            END;
            $function$
            ;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0149_building_addresses_internal_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="BuildingAddressesInternalIdReadOnly",
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
                (
                    "address",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="batid.address",
                        to_field="internal_id",
                    ),
                ),
                (
                    "building",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="batid.building"
                    ),
                ),
            ],
            options={
                "unique_together": {("building", "address")},
            },
        ),
        migrations.AddField(
            model_name="building",
            name="addresses_internal_read_only",
            field=models.ManyToManyField(
                blank=True,
                related_name="buildings_internal_read_only",
                through="batid.BuildingAddressesInternalIdReadOnly",
                to="batid.address",
            ),
        ),
        migrations.RunSQL(
            NEW_KEEP_BUILDING_ADDRESS_LINK_UPDATED_SQL,  # nosec
            reverse_sql=OLD_KEEP_BUILDING_ADDRESS_LINK_UPDATED_SQL,  # nosec
        ),
    ]
