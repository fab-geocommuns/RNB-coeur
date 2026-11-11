from django.db import migrations

# Second step of making batid_building.shape NOT NULL (see 0162).
#
# VALIDATE CONSTRAINT scans the ~51 M rows (several minutes in production) under
# SHARE UPDATE EXCLUSIVE: reads and writes go on, only other DDL, VACUUM and
# ANALYZE on batid_building wait. It runs in its own migration, hence its own
# transaction, so that the ACCESS EXCLUSIVE lock of 0162 is released before the
# scan starts.
#
# migrate runs with the app statement_timeout (5 s), which the scan does not fit
# in: it is lifted here. lock_timeout still bounds the wait for the lock.
#
# If the scan finds a NULL shape, the migration fails and the deploy stops
# before the new code is rolled out; fix the row(s) and deploy again.
#
# VALIDATE on an already valid constraint is a no-op, so the scan can also be run
# by hand beforehand, at a quiet hour, which makes this migration instant:
#     ALTER TABLE batid_building VALIDATE CONSTRAINT batid_building_shape_not_null;


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0162_building_shape_not_null_check"),
    ]

    operations = [
        migrations.RunSQL(
            """
            SET statement_timeout = '0';
            SET lock_timeout = '5s';
            ALTER TABLE batid_building
                VALIDATE CONSTRAINT batid_building_shape_not_null;
            """,
            # A validated constraint cannot be marked NOT VALID again; reverting
            # 0162 drops it.
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
