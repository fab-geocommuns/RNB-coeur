# Generated by Django 4.1.7 on 2023-10-31 15:57
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("batid", "0056_remove_bdnbbdtopo_id_and_alter_bdg_shape"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidate",
            name="is_shape_fictive",
            field=models.BooleanField(null=True),
        ),
    ]
