from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models

# Covering index for the contribution summary (GET /api/alpha/contributions/
# summaries/): it counts the distinct events of each city in one pass, read
# from the index alone. About 60 MB for 1.3 million rows.
#
# CONCURRENTLY: the inserts into batid_summerchallenge (every contribution
# writes some) are not blocked while the index is built. The previous code
# does not use it, so it runs unchanged during the deploy.


class Migration(migrations.Migration):

    atomic = False
    dependencies = [
        ("batid", "0162_drop_shape_geography_indexes"),
    ]

    operations = [
        migrations.RunSQL(
            "SET statement_timeout = '0';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        AddIndexConcurrently(
            model_name="summerchallenge",
            index=models.Index(
                condition=models.Q(("city__isnull", False)),
                fields=["city", "event_id"],
                include=("created_at", "user"),
                name="sc_city_event_idx",
            ),
        ),
    ]
