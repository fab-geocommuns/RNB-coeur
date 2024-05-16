from django.db import connection

# this procedure is used to populate the addresses_id field in the Building model
# using the current MTM relationship with the Address model
# it should be used only once and has been created as a task to avoid any client disconnection durinf the migration
# that could lead to a partial migration
# and to be able to test it as well
def launch_procedure():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DO LANGUAGE PLPGSQL $$
            DECLARE
                min_id bigint; max_id bigint;
            BEGIN
                ALTER TABLE public.batid_building DISABLE TRIGGER building_versioning_trigger;
                SELECT COALESCE(max(building_id), 0) INTO min_id FROM batid_buildingaddressesreadonly bb ;
                SELECT max(id) INTO max_id FROM batid_building where addresses_id IS NULL;

                RAISE INFO 'working from % to %', min_id, max_id;

                FOR j IN min_id..max_id LOOP
                    update batid_building bb set addresses_id = coalesce((select array_agg(address_id) from batid_building_addresses bba where building_id = bb.id group by building_id), '{}')
                    where bb.id = j;
                    if (j % 10000 = 0) then
                        COMMIT;
                        RAISE INFO 'committing data from % to % at %', j - 10000,j,now();
                    end if;
                END LOOP;
                COMMIT;
                ALTER TABLE public.batid_building ENABLE TRIGGER building_versioning_trigger;
            END;
            $$;
        """
        )
