from django.db import transaction, connection
from batid.models import Building


def delete_to_deactivate():
    disable_trigger_sql = f"ALTER TABLE {Building._meta.db_table} DISABLE TRIGGER building_versioning_trigger;"
    update_building_sql = f"""
        WITH select_bdgs AS (
            SELECT id FROM {Building._meta.db_table} 
            WHERE event_type = 'delete' OR event_type = 'deletion'
            LIMIT 1000
        )
        UPDATE {Building._meta.db_table} bdg
        SET event_type = 'deactivation'
        FROM select_bdgs
        WHERE bdg.id = select_bdgs.id
    """
    enable_trigger_sql = f"ALTER TABLE {Building._meta.db_table} ENABLE TRIGGER building_versioning_trigger;"

    loop_again = True

    while loop_again:
        with transaction.atomic():
            with connection.cursor() as cursor:

                cursor.execute(disable_trigger_sql)
                cursor.execute(update_building_sql)
                cursor.execute(enable_trigger_sql)

                # Check if we have to continue the loop
                loop_again = cursor.rowcount > 0
