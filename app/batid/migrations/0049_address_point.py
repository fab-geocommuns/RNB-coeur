# Generated by Django 4.1.7 on 2023-07-07 08:23

import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('batid', '0048_address_remove_candidate_addresses_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='address',
            name='point',
            field=django.contrib.gis.db.models.fields.PointField(null=True, srid=2154),
        ),
    ]