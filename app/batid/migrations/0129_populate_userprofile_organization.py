from django.db import migrations


def populate_organization(apps, schema_editor):
    Organization = apps.get_model("batid", "Organization")
    UserProfile = apps.get_model("batid", "UserProfile")

    for org in Organization.objects.prefetch_related("users").order_by("pk"):
        for user in org.users.all():
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if profile.organization_id is None:
                profile.organization = org
                profile.save(update_fields=["organization"])


def reverse_populate(apps, schema_editor):
    UserProfile = apps.get_model("batid", "UserProfile")
    UserProfile.objects.update(organization=None)


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0128_userprofile_organization"),
    ]

    operations = [
        migrations.RunPython(populate_organization, reverse_populate),
    ]
