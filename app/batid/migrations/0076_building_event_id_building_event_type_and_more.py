# Generated by Django 4.1.7 on 2024-03-19 14:55
import django.contrib.postgres.indexes
import django.db.models.deletion
from django.conf import settings
from django.db import migrations
from django.db import models

from batid.migrations.utils.create_view import sql_migration_building_with_history


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("batid", "0075_rename_last_updated_by_building_event_origin_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="building",
            name="event_id",
            field=models.UUIDField(db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="building",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("creation", "creation"),
                    ("update", "update"),
                    ("deletion", "deletion"),
                    ("merge", "merge"),
                    ("split", "split"),
                ],
                db_index=True,
                max_length=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="building",
            name="event_user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="building",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AddField(
            model_name="buildinghistoryonly",
            name="event_id",
            field=models.UUIDField(db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="buildinghistoryonly",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("creation", "creation"),
                    ("update", "update"),
                    ("deletion", "deletion"),
                    ("merge", "merge"),
                    ("split", "split"),
                ],
                db_index=True,
                max_length=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="buildinghistoryonly",
            name="event_user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="buildinghistoryonly",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AddField(
            model_name="contribution",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "pending"),
                    ("fixed", "fixed"),
                    ("refused", "refused"),
                ],
                db_index=True,
                default="pending",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="contribution",
            name="status_changed_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.AddIndex(
            model_name="building",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["event_origin"], name="bdg_event_origin_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="buildinghistoryonly",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["event_origin"], name="bdg_history_event_origin_idx"
            ),
        ),
        sql_migration_building_with_history(),
    ]