# Generated by Django 4.1.7 on 2023-11-20 10:52
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("batid", "0060_remove_building_shape_alter_address_point_and_more"),
    ]
    # we called the field shape_wgs84 to ease refactoring
    # we give it back its original name
    operations = [
        migrations.RenameField(
            model_name="building",
            old_name="shape_wgs84",
            new_name="shape",
        ),
    ]
