import json

from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.contrib.gis.db import models
from django.utils.timezone import now
from django.conf import settings


class Building(models.Model):
    rnb_id = models.CharField(max_length=17, null=False, unique=True, db_index=True)
    source = models.CharField(max_length=10, null=False, db_index=True)

    point = models.PointField(null=True, spatial_index=True, srid=settings.DEFAULT_SRID)
    shape = models.MultiPolygonField(
        null=True, spatial_index=True, srid=settings.DEFAULT_SRID
    )

    children = models.ManyToManyField(
        "self", blank=True, symmetrical=False, related_name="parents"
    )
    addresses = models.ManyToManyField("Address", blank=True, related_name="buildings")

    ext_bdnb_id = models.CharField(max_length=40, null=True, unique=True, db_index=True)
    ext_bdtopo_id = models.CharField(
        max_length=40, null=True, unique=True, db_index=True
    )

    def point_geojson(self):
        # todo : is there a better way to go from a PointField to geojson dict ?
        # We are doing points > dict > json str > dict. It is inefficient.
        return json.loads(self.point.transform(4326, clone=True).geojson)

    def point_lat(self):
        return self.point_geojson()["coordinates"][1]

    def point_lng(self):
        return self.point_geojson()["coordinates"][0]

    class Meta:
        ordering = ["rnb_id"]


class ADS(models.Model):
    issue_number = models.CharField(
        max_length=40, null=False, unique=True, db_index=True
    )
    issue_date = models.DateField(null=True)
    insee_code = models.CharField(max_length=5, null=True)

    class Meta:
        ordering = ["issue_date"]


class BuildingADS(models.Model):
    building = models.ForeignKey(Building, on_delete=models.CASCADE)
    ads = models.ForeignKey(
        ADS, related_name="buildings_operations", on_delete=models.CASCADE
    )
    operation = models.CharField(max_length=10, null=False)

    class Meta:
        unique_together = ("building", "ads")


class Address(models.Model):
    id = models.CharField(max_length=40, primary_key=True)
    source = models.CharField(max_length=10, null=False)  # BAN or other origin

    street_number = models.CharField(max_length=10, null=True)
    street_rep = models.CharField(max_length=5, null=True)
    street_name = models.CharField(max_length=100, null=True)
    street_type = models.CharField(max_length=100, null=True)
    city_name = models.CharField(max_length=100, null=True)
    city_zipcode = models.CharField(max_length=5, null=True)


class Candidate(models.Model):
    shape = models.MultiPolygonField(null=True, srid=settings.DEFAULT_SRID)
    source = models.CharField(max_length=20, null=False)
    source_id = models.CharField(max_length=40, null=False)
    address_keys = ArrayField(models.CharField(max_length=40), null=True)
    is_light = models.BooleanField(null=True)
    created_at = models.DateTimeField(default=now, null=True)
    inspected_at = models.DateTimeField(null=True)
    inspect_result = models.CharField(max_length=20, null=True, db_index=True)


class City(models.Model):
    id = models.AutoField(primary_key=True)
    code_insee = models.CharField(max_length=10, null=False, db_index=True)
    uri_insee = models.CharField(max_length=200, null=True)
    created_at = models.DateTimeField(null=False)
    name = models.CharField(max_length=200, null=False, db_index=True)
    name_without_article = models.CharField(max_length=200, null=False)


class Organization(models.Model):
    name = models.CharField(max_length=100, null=False)
    users = models.ManyToManyField(User, related_name="organizations")
    managed_cities = ArrayField(models.CharField(max_length=6), null=True)
