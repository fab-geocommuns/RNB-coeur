# Generated by Django 4.1.7 on 2023-09-26 08:25
import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0054_merge_0053_alter_address_street_rep_0053_plot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="plot",
            name="shape",
            field=django.contrib.gis.db.models.fields.MultiPolygonField(
                null=True, srid=2154
            ),
        ),
    ]
