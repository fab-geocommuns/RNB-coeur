from django.db import migrations

# The versioning trigger is now conditional: it does not fire when the
# "rnb.disable_building_versioning" session setting is truthy. This makes it
# possible to skip historisation inside a single transaction (see
# batid.utils.db.building_versioning_disabled), instead of
# "ALTER TABLE ... DISABLE TRIGGER" which disables the trigger for every
# session and locks the building table.
#
# The setting is read with the "missing_ok" flavour of current_setting(), so an
# unset setting returns NULL and the trigger fires as usual. A value that is not
# a valid boolean raises an error: better a failing write than a silently
# unhistoricized one.
CONDITIONAL_TRIGGER = """
    CREATE OR REPLACE TRIGGER building_versioning_trigger
    BEFORE INSERT OR UPDATE OR DELETE ON batid_building
    FOR EACH ROW
    WHEN (
        NOT COALESCE(
            NULLIF(current_setting('rnb.disable_building_versioning', true), '')::boolean,
            false
        )
    )
    EXECUTE PROCEDURE versioning('sys_period', 'batid_building_history', true);
"""

UNCONDITIONAL_TRIGGER = """
    CREATE OR REPLACE TRIGGER building_versioning_trigger
    BEFORE INSERT OR UPDATE OR DELETE ON batid_building
    FOR EACH ROW
    EXECUTE PROCEDURE versioning('sys_period', 'batid_building_history', true);
"""


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0145_userprofile_comment_from_reviewer"),
    ]

    operations = [
        migrations.RunSQL(
            CONDITIONAL_TRIGGER,
            reverse_sql=UNCONDITIONAL_TRIGGER,
        ),
    ]
