from django.db import migrations, models
from django.db.models import Func, Value

# First step of the migration of the building <-> address link towards an
# internal key (see specs/migration_lien_batiment_adresse.md).
#
# The column is only created here. Nothing reads or writes it yet: existing rows
# are filled by the fill_address_internal_id task, and the unique index and the
# NOT NULL constraint come in a later migration, once that task has run.
ADD_INTERNAL_ID = """
    -- Bare ADD COLUMN. A DEFAULT nextval() at this point would be a volatile
    -- default and would rewrite the whole table under ACCESS EXCLUSIVE.
    ALTER TABLE batid_address ADD COLUMN internal_id bigint;

    -- OWNED BY ties the sequence to the column: dropping one drops the other.
    -- This is the layout Django creates for a BigAutoField (bigserial), which
    -- is what internal_id eventually becomes when it takes over as primary key.
    CREATE SEQUENCE batid_address_internal_id_seq AS bigint
        OWNED BY batid_address.internal_id;

    -- Catalog-only change, no table rewrite. It is set before the backfill on
    -- purpose: rows inserted while the backfill runs already get an internal_id,
    -- so the backfill never has to be run a second time to catch them.
    ALTER TABLE batid_address
        ALTER COLUMN internal_id SET DEFAULT nextval('batid_address_internal_id_seq');
"""

DROP_INTERNAL_ID = """
    -- Dropping the column drops its default and, through OWNED BY, the sequence.
    ALTER TABLE batid_address DROP COLUMN internal_id;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0146_conditional_building_versioning_trigger"),
    ]

    operations = [
        migrations.RunSQL(
            "SET statement_timeout = '0';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(ADD_INTERNAL_ID, reverse_sql=DROP_INTERNAL_ID),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="address",
                    name="internal_id",
                    field=models.BigIntegerField(
                        db_default=Func(
                            Value("batid_address_internal_id_seq"),
                            function="nextval",
                            output_field=models.BigIntegerField(),
                        ),
                        editable=False,
                        null=True,
                    ),
                ),
            ],
        ),
    ]
