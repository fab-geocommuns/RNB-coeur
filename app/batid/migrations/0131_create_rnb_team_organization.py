from django.db import migrations

# Hardcoded by design — data migrations must not import from settings.
# If this name changes, create a new data migration AND update settings.RNB_TEAM_ORG_NAME.
_ORG_NAME = "Équipe RNB"


def create_rnb_team_org(apps, schema_editor):
    Organization = apps.get_model("batid", "Organization")
    Organization.objects.get_or_create(name=_ORG_NAME)


def reverse_rnb_team_org(apps, schema_editor):
    Organization = apps.get_model("batid", "Organization")
    Organization.objects.filter(name=_ORG_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0130_userprofile_organization"),
    ]

    operations = [
        migrations.RunPython(create_rnb_team_org, reverse_rnb_team_org),
    ]
