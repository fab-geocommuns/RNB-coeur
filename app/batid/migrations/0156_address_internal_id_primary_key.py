import django.db.models.deletion
from django.db import migrations, models

# Last step of the migration of the building <> address link towards an internal
# key: internal_id becomes the primary key of batid_address, and cle_interop
# (the BAN "clé d'interopérabilité") a plain UNIQUE column.
#
# Everything is catalog-only, the work was done by the previous migrations:
# - cle_interop already has its own unique index (0155), which is promoted to a
#   UNIQUE constraint;
# - internal_id already has a unique index (0148), which is promoted to the
#   primary key. USING INDEX is accepted because that index, declared as an
#   expression in Meta.constraints on purpose, is not owned by any constraint.
#   It keeps its identity through the promotion, so the foreign key of
#   batid_buildingaddressesinternalidreadonly, which depends on it, is untouched
#   (and the foreign key already targets internal_id: its to_field disappears
#   from the state only).
#
# The old primary key is dropped first, which drops its index. The
# varchar_pattern_ops index Django created next to it (batid_address_id_..._like)
# is a separate index and stays: it serves the startswith lookups on cle_interop.
#
# All in one transaction: there is no moment without a primary key, and no
# moment without a unique index on cle_interop.
#
# Like 0148, the migration runs in the entrypoint of the web container, with the
# app statement_timeout (5 s). ACCESS EXCLUSIVE is taken on batid_address and
# waits for the transactions in flight, blocking every query behind it:
# lock_timeout makes the migration fail fast and roll back.
#
# Irreversible on purpose: going back would mean dropping the primary key that
# the foreign key of the join table depends on, hence rebuilding both.

PRIMARY_KEY_SWITCH = """
    SET statement_timeout = '0';
    SET lock_timeout = '5s';

    ALTER TABLE batid_address DROP CONSTRAINT batid_address_pkey;

    ALTER TABLE batid_address
        ADD CONSTRAINT batid_address_cle_interop_key
        UNIQUE USING INDEX batid_address_cle_interop_uniq;

    ALTER TABLE batid_address
        ADD CONSTRAINT batid_address_pkey
        PRIMARY KEY USING INDEX batid_address_internal_id_uniq;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0155_address_cle_interop_unique_index"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # No reverse_sql: this is what makes the migration irreversible.
            database_operations=[migrations.RunSQL(PRIMARY_KEY_SWITCH)],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="address",
                    name="batid_address_internal_id_uniq",
                ),
                migrations.AlterField(
                    model_name="address",
                    name="cle_interop",
                    field=models.CharField(max_length=40, unique=True),
                ),
                migrations.AlterField(
                    model_name="address",
                    name="internal_id",
                    field=models.BigAutoField(primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name="buildingaddressesinternalidreadonly",
                    name="address",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="batid.address",
                    ),
                ),
            ],
        ),
    ]
