# Generated by Django 4.1.7 on 2023-03-10 08:20
import django.contrib.gis.db.models.fields
import django.utils.timezone
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0010_alter_candidate_created_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="candidate",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name="candidate",
            name="shape",
            field=django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326),
        ),
    ]
