# Generated by Django 4.1.7 on 2023-04-04 09:00
import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0015_alter_candidate_inspect_result"),
    ]

    operations = [
        migrations.CreateModel(
            name="ADS",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "issue_number",
                    models.CharField(db_index=True, max_length=40, unique=True),
                ),
                ("issue_date", models.DateField(null=True)),
            ],
        ),
        migrations.CreateModel(
            name="BuildingADS",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("operation", models.CharField(max_length=10)),
                (
                    "ads",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="batid.ads"
                    ),
                ),
                (
                    "building",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="batid.building"
                    ),
                ),
            ],
            options={
                "unique_together": {("building", "ads")},
            },
        ),
    ]
