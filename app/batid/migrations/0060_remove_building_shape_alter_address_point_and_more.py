# Generated by Django 4.1.7 on 2023-11-16 15:12
import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("batid", "0059_buildingimport_building_last_updated_by_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="building",
            name="shape",
        ),
        migrations.RunSQL(
            """
                ALTER TABLE batid_address
                ALTER COLUMN point
                TYPE Geometry(point, 4326)
                USING ST_Transform(point, 4326);
            """,
            reverse_sql="""
                ALTER TABLE batid_address
                ALTER COLUMN point
                TYPE Geometry(point, 2154)
                USING ST_Transform(point, 2154);
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="address",
                    name="point",
                    field=django.contrib.gis.db.models.fields.PointField(
                        null=True, srid=4326
                    ),
                )
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE batid_building
                ALTER COLUMN point
                TYPE Geometry(point, 4326)
                USING ST_Transform(point, 4326);
            """,
            reverse_sql="""
                ALTER TABLE batid_building
                ALTER COLUMN point
                TYPE Geometry(point, 2154)
                USING ST_Transform(point, 2154);
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="building",
                    name="point",
                    field=django.contrib.gis.db.models.fields.PointField(
                        null=True, srid=4326
                    ),
                )
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE batid_candidate
                ALTER COLUMN shape
                TYPE Geometry(multipolygon, 4326)
                USING ST_Transform(shape, 4326);
            """,
            reverse_sql="""
                ALTER TABLE batid_candidate
                ALTER COLUMN shape
                TYPE Geometry(multipolygon, 2154)
                USING ST_Transform(shape, 2154);
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="candidate",
                    name="shape",
                    field=django.contrib.gis.db.models.fields.MultiPolygonField(
                        null=True, srid=4326
                    ),
                )
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE batid_city
                ALTER COLUMN shape
                TYPE Geometry(multipolygon, 4326)
                USING ST_Transform(shape, 4326);
            """,
            reverse_sql="""
                ALTER TABLE batid_city
                ALTER COLUMN shape
                TYPE Geometry(multipolygon, 2154)
                USING ST_Transform(shape, 2154);
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="city",
                    name="shape",
                    field=django.contrib.gis.db.models.fields.MultiPolygonField(
                        null=True, srid=4326
                    ),
                )
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE batid_department
                ALTER COLUMN shape
                TYPE Geometry(multipolygon, 4326)
                USING ST_Transform(shape, 4326);
            """,
            reverse_sql="""
                ALTER TABLE batid_department
                ALTER COLUMN shape
                TYPE Geometry(multipolygon, 2154)
                USING ST_Transform(shape, 2154);
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="department",
                    name="shape",
                    field=django.contrib.gis.db.models.fields.MultiPolygonField(
                        null=True, srid=4326
                    ),
                )
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE batid_plot
                ALTER COLUMN shape
                TYPE Geometry(multipolygon, 4326)
                USING ST_Transform(shape, 4326);
            """,
            reverse_sql="""
                ALTER TABLE batid_plot
                ALTER COLUMN shape
                TYPE Geometry(multipolygon, 2154)
                USING ST_Transform(shape, 2154);
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="plot",
                    name="shape",
                    field=django.contrib.gis.db.models.fields.MultiPolygonField(
                        null=True, srid=4326
                    ),
                )
            ],
        ),
    ]
