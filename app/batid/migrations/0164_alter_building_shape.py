import django.contrib.gis.db.models.fields
from django.db import migrations

# Last step of making batid_building.shape NOT NULL (see 0162).
#
# SET NOT NULL does not scan the table: PostgreSQL (12+) proves it from the
# CHECK (shape IS NOT NULL) validated by 0163. The CHECK is then redundant and
# dropped. Both statements are catalog-only but take ACCESS EXCLUSIVE for an
# instant, hence lock_timeout.
#
# The SQL is written by hand rather than left to AlterField so that it is
# exactly these two statements.


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0163_building_shape_not_null_validate"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    """
                    SET lock_timeout = '5s';
                    ALTER TABLE batid_building ALTER COLUMN shape SET NOT NULL;
                    ALTER TABLE batid_building
                        DROP CONSTRAINT batid_building_shape_not_null;
                    """,
                    reverse_sql="""
                    SET lock_timeout = '5s';
                    ALTER TABLE batid_building
                        ADD CONSTRAINT batid_building_shape_not_null
                        CHECK (shape IS NOT NULL);
                    ALTER TABLE batid_building ALTER COLUMN shape DROP NOT NULL;
                    """,
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="building",
                    name="shape",
                    field=django.contrib.gis.db.models.fields.GeometryField(
                        spatial_index=True, srid=4326
                    ),
                ),
            ],
        ),
    ]
