# Generated manually
from django.db import migrations
from django.db import models

forward_backfill_contribution_counts_sql = """
    WITH contributions_per_user AS (
        SELECT review_user_id, COUNT(*) AS total_contributions
        FROM batid_contribution
        WHERE review_user_id IS NOT NULL AND report = false
        GROUP BY review_user_id
    )
    UPDATE batid_userprofile
    SET total_contributions = contributions_per_user.total_contributions
    FROM contributions_per_user
    WHERE batid_userprofile.user_id = contributions_per_user.review_user_id;
    """

reverse_backfill_contribution_counts_sql = """
    UPDATE batid_userprofile
    SET total_contributions = 0;
    """


def create_missing_user_profiles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("batid", "UserProfile")
    count = 0
    for user in User.objects.prefetch_related("profile").all():
        if not hasattr(user, "profile"):
            UserProfile.objects.create(user=user)
            count += 1
    print(f"Created {count} missing user profiles")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0113_migrate_contributions_to_report"),
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
        migrations.RunPython(create_missing_user_profiles, noop),
        migrations.RunSQL(
            forward_backfill_contribution_counts_sql,
            reverse_backfill_contribution_counts_sql,
        ),
    ]
