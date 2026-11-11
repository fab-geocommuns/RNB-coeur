from django.db import migrations

# First step of making batid_building.shape NOT NULL without downtime (51 M rows).
#
# A plain SET NOT NULL scans the whole table under ACCESS EXCLUSIVE, which would
# block the API for the whole scan. Instead:
# - 0162 (this one) adds a CHECK (shape IS NOT NULL) NOT VALID: catalog-only, it
#   rejects new NULLs right away but does not look at the existing rows;
# - 0163 validates it: full scan, but under SHARE UPDATE EXCLUSIVE, which does
#   not block reads or writes;
# - 0164 runs SET NOT NULL, which PostgreSQL proves from the validated CHECK
#   without scanning again, then drops the CHECK.
#
# The previous code never writes a NULL shape (create_new requires it, save() is
# forbidden outside tests), so it runs fine on the constrained table.
#
# ADD CONSTRAINT takes ACCESS EXCLUSIVE for an instant: lock_timeout makes the
# migration fail fast rather than queue the API behind it.


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0161_emailnotificationoptout"),
    ]

    operations = [
        migrations.RunSQL(
            """
            SET lock_timeout = '5s';
            ALTER TABLE batid_building
                ADD CONSTRAINT batid_building_shape_not_null
                CHECK (shape IS NOT NULL) NOT VALID;
            """,
            reverse_sql="""
            SET lock_timeout = '5s';
            ALTER TABLE batid_building
                DROP CONSTRAINT batid_building_shape_not_null;
            """,
        ),
    ]
