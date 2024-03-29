# Generated by Django 4.1.7 on 2024-03-07 14:16
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0073_create_index_geographic_index_bdg_plots"),
    ]

    operations = [
        migrations.AddField(
            model_name="building",
            name="status",
            field=models.CharField(
                choices=[
                    ("constructionProject", "En projet"),
                    ("canceledConstructionProject", "Projet annulé"),
                    ("ongoingConstruction", "Construction en cours"),
                    ("constructed", "Construit"),
                    ("ongoingChange", "En cours de modification"),
                    ("notUsable", "Non utilisable"),
                    ("demolished", "Démoli"),
                ],
                db_index=True,
                default="constructed",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="buildinghistoryonly",
            name="status",
            field=models.CharField(
                choices=[
                    ("constructionProject", "En projet"),
                    ("canceledConstructionProject", "Projet annulé"),
                    ("ongoingConstruction", "Construction en cours"),
                    ("constructed", "Construit"),
                    ("ongoingChange", "En cours de modification"),
                    ("notUsable", "Non utilisable"),
                    ("demolished", "Démoli"),
                ],
                db_index=True,
                default="constructed",
                max_length=30,
            ),
        ),
        migrations.DeleteModel(
            name="BuildingStatus",
        ),
        migrations.RunSQL(
            """
            DROP VIEW IF EXISTS batid_building_with_history;
            create view batid_building_with_history as
            select null as bh_id, * from batid_building
            union all
            select * from batid_building_history;
            """,
            reverse_sql="""
            DROP VIEW IF EXISTS batid_building_with_history;
            create view batid_building_with_history as
            select null as bh_id, * from batid_building
            union all
            select * from batid_building_history;
            """,
        ),
    ]
