import json

from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.contrib.gis.db import models
from django.conf import settings
from django.db.models import F


class Building(models.Model):
    rnb_id = models.CharField(max_length=12, null=False, unique=True, db_index=True)
    source = models.CharField(max_length=10, null=False, db_index=True)

    point = models.PointField(null=True, spatial_index=True, srid=settings.DEFAULT_SRID)
    shape = models.MultiPolygonField(
        null=True, spatial_index=True, srid=settings.DEFAULT_SRID
    )

    addresses = models.ManyToManyField("Address", blank=True, related_name="buildings")

    ext_bdnb_id = models.CharField(max_length=40, null=True, db_index=True)
    ext_bdtopo_id = models.CharField(max_length=40, null=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def point_geojson(self):
        # todo : is there a better way to go from a PointField to geojson dict ?
        # We are doing points > dict > json str > dict. It is inefficient.
        return json.loads(self.point.transform(4326, clone=True).geojson)

    def ads_geojson(self):
        return json.loads(self.point.transform(4326, clone=True).geojson)

    def point_lat(self):
        return self.point_geojson()["coordinates"][1]

    def point_lng(self):
        return self.point_geojson()["coordinates"][0]

    @property
    def current_status(self):
        return self.status.filter(is_current=True).first()

    class Meta:
        ordering = ["rnb_id"]


class BuildingStatus(models.Model):
    CONSTRUCTION_PROJECT = 0
    CANCELED_CONSTRUCTION_PROJECT = 1
    ONGOING_CONSTRUCTION = 2
    CONSTRUCTED = 3
    ONGOING_CHANGE = 4
    NOT_USABLE = 5
    DEMOLISHED = 6

    TYPES = (
        (CONSTRUCTION_PROJECT, "constructionProject"),
        (CANCELED_CONSTRUCTION_PROJECT, "canceledConstructionProject"),
        (ONGOING_CONSTRUCTION, "ongoingConstruction"),
        (CONSTRUCTED, "constructed"),
        (ONGOING_CHANGE, "ongoingChange"),
        (NOT_USABLE, "notUsable"),
        (DEMOLISHED, "demolished"),
    )

    id = models.AutoField(primary_key=True)
    # type = models.CharField(
    #     choices=BuildingStatusModel.TYPES_CHOICES,
    #     null=False,
    #     db_index=True,
    #     max_length=30,
    # )

    type = models.IntegerField(choices=TYPES, default=CONSTRUCTED)

    happened_at = models.DateField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_current = models.BooleanField(null=False, default=False)
    building = models.ForeignKey(
        Building, related_name="status", on_delete=models.CASCADE
    )

    class Meta:
        ordering = [F("happened_at").asc(nulls_first=True)]

    @property
    def label(self):
        return self.int_to_label(self.type)

    @classmethod
    def int_to_label(cls, status_int):
        for t_int, t_label in cls.TYPES:
            if t_int == status_int:
                return t_label

    @classmethod
    def label_to_int(cls, status_label):
        for t_int, t_label in cls.TYPES:
            if t_label == status_label:
                return t_int

    def save(self, *args, **kwargs):
        # If the status is current, we make sure that the previous current status is not current anymore
        if self.is_current:
            self.building.status.filter(is_current=True).update(is_current=False)
        super().save(*args, **kwargs)


class City(models.Model):
    id = models.AutoField(primary_key=True)
    code_insee = models.CharField(max_length=10, null=False, db_index=True, unique=True)
    name = models.CharField(max_length=200, null=False, db_index=True)
    shape = models.MultiPolygonField(
        null=True, spatial_index=True, srid=settings.DEFAULT_SRID
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Department(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=3, null=False, db_index=True, unique=True)
    name = models.CharField(max_length=200, null=False)
    shape = models.MultiPolygonField(
        null=True, spatial_index=True, srid=settings.DEFAULT_SRID
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ADSAchievement(models.Model):
    file_number = models.CharField(
        max_length=40, null=False, unique=True, db_index=True
    )
    achieved_at = models.DateField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ADS(models.Model):
    file_number = models.CharField(
        max_length=40, null=False, unique=True, db_index=True
    )
    decided_at = models.DateField(null=True)
    city = models.ForeignKey(City, on_delete=models.CASCADE, null=True)
    achieved_at = models.DateField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    creator = models.ForeignKey(User, on_delete=models.CASCADE, null=True)

    class Meta:
        ordering = ["decided_at"]


class BuildingADS(models.Model):
    building = models.ForeignKey(Building, on_delete=models.CASCADE)
    ads = models.ForeignKey(
        ADS, related_name="buildings_operations", on_delete=models.CASCADE
    )

    operation = models.CharField(max_length=10, null=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    creator = models.ForeignKey(User, on_delete=models.CASCADE, null=True)

    class Meta:
        unique_together = ("building", "ads")


class Candidate(models.Model):
    shape = models.MultiPolygonField(null=True, srid=settings.DEFAULT_SRID)
    source = models.CharField(max_length=20, null=False)
    source_id = models.CharField(max_length=40, null=False)
    address_keys = ArrayField(models.CharField(max_length=40), null=True)
    # information coming from the BDTOPO
    # see https://geoservices.ign.fr/sites/default/files/2021-07/DC_BDTOPO_3-0.pdf
    # Indique qu'il s'agit d'une structure légère, non attachée au sol par l'intermédiaire de fondations, ou d'un
    # bâtiment ou partie de bâtiment ouvert sur au moins un côté.
    is_light = models.BooleanField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # The inspect_stamp is a DIY lock system to ensure a candidate is not inspected twice
    # It MIGHT be replaced by systems closer to the db (eg : SELECT ... FOR UPDATE and postegresql LOCK system)
    # but I do not know those enough to use them right now.
    inspect_stamp = models.CharField(max_length=20, null=True, db_index=True)
    inspected_at = models.DateTimeField(null=True)
    inspect_result = models.CharField(max_length=20, null=True, db_index=True)


class Plot(models.Model):
    id = models.CharField(max_length=40, primary_key=True, db_index=True)
    shape = models.MultiPolygonField(null=True, srid=settings.DEFAULT_SRID)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Address(models.Model):
    id = models.CharField(max_length=40, primary_key=True, db_index=True)
    source = models.CharField(max_length=10, null=False)  # BAN or other origin

    point = models.PointField(null=True, spatial_index=True, srid=settings.DEFAULT_SRID)

    street_number = models.CharField(max_length=10, null=True)
    street_rep = models.CharField(max_length=10, null=True)
    street_name = models.CharField(max_length=100, null=True)
    street_type = models.CharField(max_length=100, null=True)
    city_name = models.CharField(max_length=100, null=True)
    city_zipcode = models.CharField(max_length=5, null=True)
    city_insee_code = models.CharField(max_length=5, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Organization(models.Model):
    name = models.CharField(max_length=100, null=False)
    users = models.ManyToManyField(User, related_name="organizations")
    managed_cities = ArrayField(models.CharField(max_length=6), null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AsyncSignal(models.Model):
    id = models.AutoField(primary_key=True)
    type = models.CharField(max_length=20, null=False, db_index=True)
    building = models.ForeignKey(Building, on_delete=models.CASCADE, null=True)
    origin = models.CharField(max_length=100, null=False, db_index=True)
    handled_at = models.DateTimeField(null=True)
    handle_result = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    creator_copy_id = models.IntegerField(null=True)
    creator_copy_fname = models.CharField(max_length=100, null=True)
    creator_copy_lname = models.CharField(max_length=100, null=True)
    creator_org_copy_id = models.IntegerField(null=True)
    creator_org_copy_name = models.CharField(max_length=100, null=True)

    class Meta:
        ordering = ["created_at"]
