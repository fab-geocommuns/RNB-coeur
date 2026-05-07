from django.db import migrations


def clear_ban_id(apps, schema_editor):
    Address = apps.get_model("batid", "Address")
    Address.objects.exclude(ban_id=None).update(ban_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0130_remove_organization_users"),
    ]

    operations = [
        migrations.RunPython(clear_ban_id, reverse_code=migrations.RunPython.noop),
    ]
