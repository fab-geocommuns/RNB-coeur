# Generated by Django 4.1.7 on 2023-06-08 09:36
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0039_adsachievement_delete_adsend_and_more"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Signal",
            new_name="AsyncSignal",
        ),
        migrations.AlterModelOptions(
            name="asyncsignal",
            options={"ordering": ["created_at"]},
        ),
    ]
