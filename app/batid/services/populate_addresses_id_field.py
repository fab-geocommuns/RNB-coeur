from django.db import connection


def launch_procedure():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DO LANGUAGE PLPGSQL $$
            DECLARE
                min_id bigint; max_id bigint;
            BEGIN
                SELECT min(id), max(id) INTO min_id, max_id FROM batid_building;
                FOR j IN min_id..max_id LOOP
                    update batid_building bb set addresses_id = (select array_agg(address_id) from batid_building_addresses bba where building_id = bb.id group by building_id)
                    where bb.id = j;
	                if (j % 1000 = 0) then
	                    RAISE INFO 'committing data from % to % at %', j - 1000,j,now();
	                end if;
                    COMMIT;
                END LOOP;
            END;
            $$;
        """
        )
