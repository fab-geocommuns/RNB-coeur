# Generated by Django 4.1.7 on 2023-07-06 12:58
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0046_remove_building_children_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidate",
            name="inspect_stamp",
            field=models.CharField(db_index=True, max_length=20, null=True),
        ),
    ]
