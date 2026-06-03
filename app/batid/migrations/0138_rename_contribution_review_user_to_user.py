from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0137_clean_contribution_model"),
    ]

    operations = [
        migrations.RenameField(
            model_name="contribution",
            old_name="review_user",
            new_name="user",
        ),
    ]
