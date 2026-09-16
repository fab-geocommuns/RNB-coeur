from batid.migrations.utils.create_view import sql_migration_building_with_history
from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0148_address_internal_id_constraints"),
    ]

    operations = [
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
