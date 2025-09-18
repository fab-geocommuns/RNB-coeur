import django.contrib.postgres.indexes
from django.contrib.postgres import operations
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ("batid", "0108_building_unique_rnb_id_event_type_building"),
    ]

    operations = [
        migrations.RunSQL(
            "SET statement_timeout = '3600000';",  # 60 min
            reverse_sql=migrations.RunSQL.noop,
        ),
        operations.CreateExtension("btree_gist"),
        operations.AddIndexConcurrently(
            model_name="building",
            index=django.contrib.postgres.indexes.GistIndex(
                fields=["point", "id"], name="bdg_point_id_btree_gist_idx"
            ),
        ),
        operations.AddIndexConcurrently(
            model_name="building",
            index=django.contrib.postgres.indexes.GistIndex(
                fields=["id", "point"], name="bdg_id_point_btree_gist_idx"
            ),
        ),
    ]
