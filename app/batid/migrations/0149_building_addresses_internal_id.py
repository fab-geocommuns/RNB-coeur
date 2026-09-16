from batid.migrations.utils.create_view import sql_migration_building_with_history
from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0148_address_internal_id_constraints"),
    ]

    operations = [
        # ADD COLUMN with no default is a catalog-only change, instant regardless
        # of table size — but it still takes ACCESS EXCLUSIVE on batid_building
        # and batid_building_history (same for the view drop/recreate below), so
        # it waits for any transaction in flight on those tables and blocks every
        # query arriving behind it meanwhile. batid_building is written to by
        # Celery import/backfill jobs outside of request/response cycles, so a
        # conflicting transaction here is more likely than on batid_address.
        # lock_timeout makes the migration fail fast and roll back instead.
        migrations.RunSQL(
            "SET statement_timeout = '0'; SET lock_timeout = '5s';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="building",
            name="addresses_internal_id",
            field=ArrayField(base_field=models.BigIntegerField(), null=True, size=None),
        ),
        migrations.AddField(
            model_name="buildinghistoryonly",
            name="addresses_internal_id",
            field=ArrayField(base_field=models.BigIntegerField(), null=True, size=None),
        ),
        sql_migration_building_with_history(),
    ]
