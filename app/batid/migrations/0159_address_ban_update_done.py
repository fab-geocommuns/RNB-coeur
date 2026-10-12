from django.db import migrations, models

# Nullable without default: adding the column only touches the catalog (no table
# rewrite of batid_address). Its index comes in a separate migration.


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0158_address_cle_interop_upper_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="ban_update_done",
            field=models.BooleanField(default=None, null=True),
        ),
    ]
