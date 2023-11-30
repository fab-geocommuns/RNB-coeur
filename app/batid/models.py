from email.policy import default
import json
from typing import Any, Optional

from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField, DateTimeRangeField
from django.contrib.gis.db import models
from django.conf import settings
from django.db.models import F
from batid.services.bdg_status import BuildingStatus as BuildingStatusModel
from batid.validators import validate_one_ext_id
from batid.utils.db import from_now_to_infinity


class BuildingAbstract(models.Model):
    rnb_id = models.CharField(max_length=12, null=False, unique=True, db_index=True)
    source = models.CharField(max_length=10, null=False, db_index=True)
    point = models.PointField(null=True, spatial_index=True, srid=4326)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    shape = models.GeometryField(null=True, spatial_index=True, srid=4326)
    ext_ids = models.JSONField(null=True)
    last_updated_by = models.JSONField(null=True)
    # temporal table field
    sys_period = DateTimeRangeField(null=False, default=from_now_to_infinity)
    # in case of building merge, we want in the future to keep the list of the parent buildings
    # not implemented for now
    parent_buildings = models.JSONField(null=True)

    class Meta:
        abstract = True


class Building(BuildingAbstract):
    addresses = models.ManyToManyField("Address", blank=True, related_name="buildings")

    def add_ext_id(
        self, source: str, source_version: Optional[str], id: str, created_at: str
    ):
        # Get the format
        ext_id = {
            "source": source,
            "source_version": source_version,
            "id": id,
            "created_at": created_at,
        }
        # Validate the content
        validate_one_ext_id(ext_id)

        # Init if necessary
        if not self.ext_ids:
            self.ext_ids = []

        # Append
        self.ext_ids.append(ext_id)

        # Sort by created_at
        self.ext_ids = sorted(self.ext_ids, key=lambda k: k["created_at"])

    def contains_ext_id(
        self, source: str, source_version: Optional[str], id: str
    ) -> bool:
        if not self.ext_ids:
            return False

        for ext_id in self.ext_ids:
            if (
                ext_id["source"] == source
                and ext_id["source_version"] == source_version
                and ext_id["id"] == id
            ):
                return True

        return False

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


class BuildingWithHistory(BuildingAbstract):
    # this read-only model is used to access the corresponding view
    # it contains current AND previous versions of the buildings
    class Meta:
        managed = False
        # We could add an default ordering based on the temporal field (https://docs.djangoproject.com/en/4.2/ref/models/options/#ordering). It almost sure we will have to present chronologically the history of a building
        db_table = "batid_building_with_history"


class BuildingHistoryOnly(BuildingAbstract):
    # this model is probably not going to be used in the app
    # use BuildingWithHistory instead
    # it is created only so that any change in the Building model is reflected in the history table

    # primary key for this table, because Django ORM wants one
    bh_id = models.BigAutoField(
        auto_created=True, primary_key=True, serialize=False, verbose_name="BH_ID"
    )
    # primary key coming from the Building table, but not unique here.
    id = models.BigIntegerField()
    rnb_id = models.CharField(max_length=12, null=False, unique=False, db_index=True)

    class Meta:
        managed = True
        db_table = "batid_building_history"


class BuildingStatus(models.Model):
    id = models.AutoField(primary_key=True)
    type = models.CharField(
        choices=BuildingStatusModel.TYPES_CHOICES,
        null=False,
        db_index=True,
        max_length=30,
    )
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
        return BuildingStatusModel.get_label(self.type)

    def save(self, *args, **kwargs):
        # If the status is current, we make sure that the previous current status is not current anymore
        if self.is_current:
            self.building.status.filter(is_current=True).update(is_current=False)
        super().save(*args, **kwargs)


class City(models.Model):
    id = models.AutoField(primary_key=True)
    code_insee = models.CharField(max_length=10, null=False, db_index=True, unique=True)
    name = models.CharField(max_length=200, null=False, db_index=True)
    shape = models.MultiPolygonField(null=True, spatial_index=True, srid=4326)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Department(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=3, null=False, db_index=True, unique=True)
    name = models.CharField(max_length=200, null=False)
    shape = models.MultiPolygonField(null=True, spatial_index=True, srid=4326)
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
    shape = models.GeometryField(null=True, srid=4326)
    source = models.CharField(max_length=20, null=False)
    source_version = models.CharField(max_length=20, null=True)
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
    inspected_at = models.DateTimeField(null=True, db_index=True)
    inspection_details = models.JSONField(null=True)
    created_by = models.JSONField(null=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # this field is used to store the decision of the inspector
        # but is not intended to be stored in the database
        self.inspector_decision = ""


class Plot(models.Model):
    id = models.CharField(max_length=40, primary_key=True, db_index=True)
    shape = models.MultiPolygonField(null=True, srid=4326)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Address(models.Model):
    id = models.CharField(max_length=40, primary_key=True, db_index=True)
    source = models.CharField(max_length=10, null=False)  # BAN or other origin

    point = models.PointField(null=True, spatial_index=True, srid=4326)

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


class BuildingImport(models.Model):
    id = models.AutoField(primary_key=True)
    import_source = models.CharField(max_length=20, null=False)
    # the id of the "bulk launch"
    # a bulk launch will typically launch an import on the country and will generate an import for each department
    bulk_launch_uuid = models.UUIDField(null=True)
    departement = models.CharField(max_length=3, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    # number of candidates created by the import
    candidate_created_count = models.IntegerField(null=True)
    # what happened to the candidates
    building_created_count = models.IntegerField(null=True)
    building_updated_count = models.IntegerField(null=True)
    building_refused_count = models.IntegerField(null=True)
