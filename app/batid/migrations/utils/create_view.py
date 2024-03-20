from django.db import migrations


def sql_migration_building_with_history():
    sql = """
            DROP VIEW IF EXISTS batid_building_with_history;
            create view batid_building_with_history as
            select null as bh_id, * from batid_building
            union all
            select * from batid_building_history;
            """
    return migrations.RunSQL(sql, reverse_sql=sql)
