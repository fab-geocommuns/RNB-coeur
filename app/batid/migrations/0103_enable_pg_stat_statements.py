# Generated by Django 5.2.1 on 2025-07-02 09:27
from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("batid", "0102_kpi"),
    ]

    operations = [
        CreateExtension("pg_stat_statements"),
    ]
