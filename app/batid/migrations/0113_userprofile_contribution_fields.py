# Generated manually
from django.db import migrations
from django.db import models


def backfill_total_contributions(apps, schema_editor):
    UserProfile = apps.get_model("batid", "UserProfile")
    Contribution = apps.get_model("batid", "Contribution")

    profiles = UserProfile.objects.all()

    for profile in profiles:
        contribution_count = Contribution.objects.filter(
            review_user_id=profile.user_id
        ).count()

        profile.total_contributions = contribution_count
        profile.save(update_fields=["total_contributions"])


def reverse_backfill(apps, schema_editor):
    UserProfile = apps.get_model("batid", "UserProfile")
    UserProfile.objects.all().update(total_contributions=0)


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0112_create_report_reportmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="max_allowed_contributions",
            field=models.IntegerField(default=500),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="total_contributions",
            field=models.IntegerField(default=0),
        ),
        migrations.RunPython(backfill_total_contributions, reverse_backfill),
    ]
