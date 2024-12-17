from django.db import migrations


def building_with_history_drop_view():
    return """
            DROP VIEW IF EXISTS batid_building_with_history;
            """


def building_with_history_create_view():
    return """
            create view batid_building_with_history as
            select null as bh_id, * from batid_building
            union all
            select * from batid_building_history;

        """


def sql_migration_building_with_history_drop_view():
    sql = building_with_history_drop_view()
    reverse_sql = building_with_history_create_view()

    return migrations.RunSQL(sql, reverse_sql=reverse_sql)


def sql_migration_building_with_history():
    sql = building_with_history_drop_view() + building_with_history_create_view()
    return migrations.RunSQL(sql, reverse_sql=sql)
