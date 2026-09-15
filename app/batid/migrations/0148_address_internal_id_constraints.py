from django.db import migrations, models

# Second step of the migration of the building <-> address link towards an
# internal key (see specs/migration_lien_batiment_adresse.md).
#
# 0146 created batid_address.internal_id and its DEFAULT; the addresses that
# predate it were filled by the fill_address_internal_id task. This migration
# makes the column unique and NOT NULL.
#
# ⚠ Check that the backfill is over before deploying:
#     SELECT count(*) FROM batid_address WHERE internal_id IS NULL;
# AlterField below does not fail on the rows left at NULL, it fills them from the
# sequence, so an unfinished backfill would go through unnoticed — as a mass
# UPDATE inside the migration, hence inside the entrypoint of the web container.
#
# The unique constraint is declared in Meta.constraints as an expression rather
# than as unique=True on the field, so that Django emits a bare CREATE UNIQUE
# INDEX: the primary key switch reuses that index in ADD PRIMARY KEY USING INDEX,
# which PostgreSQL refuses on an index owned by a constraint.


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0147_address_internal_id"),
    ]

    operations = [
        # migrate runs in the entrypoint of the web container, so with the 5 s
        # statement_timeout of the app, which neither statement below fits in.
        # lock_timeout takes over as the guard: both take ACCESS EXCLUSIVE on
        # batid_address, which waits for the transactions in flight and blocks
        # every query arriving behind it meanwhile. Better to fail fast and let
        # the migration roll back.
        migrations.RunSQL(
            "SET statement_timeout = '0'; SET lock_timeout = '5s';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="address",
            name="internal_id",
            field=models.BigIntegerField(
                db_default=models.Func(
                    models.Value("batid_address_internal_id_seq"),
                    function="nextval",
                    output_field=models.BigIntegerField(),
                ),
                editable=False,
            ),
        ),
        migrations.AddConstraint(
            model_name="address",
            constraint=models.UniqueConstraint(
                models.F("internal_id"), name="batid_address_internal_id_uniq"
            ),
        ),
    ]
