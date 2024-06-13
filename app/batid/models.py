import json
from typing import Optional

from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.indexes import GinIndex
from django.db.models.functions import Lower
from django.db.models.indexes import Index

from batid.services.bdg_status import BuildingStatus as BuildingStatusModel
from batid.utils.db import from_now_to_infinity
from batid.validators import validate_one_ext_id


class BuildingAbstract(models.Model):
    rnb_id = models.CharField(max_length=12, null=False, unique=True, db_index=True)
    point = models.PointField(null=True, spatial_index=True, srid=4326)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    shape = models.GeometryField(null=True, spatial_index=True, srid=4326)
    ext_ids = models.JSONField(null=True)
    event_origin = models.JSONField(null=True)
    # temporal table field
    sys_period = DateTimeRangeField(null=False, default=from_now_to_infinity)
    # in case of building merge, we want in the future to keep the list of the parent buildings
    # not implemented for now
    parent_buildings = models.JSONField(null=True)
    # enum field for the building status
    status = models.CharField(
        choices=BuildingStatusModel.TYPES_CHOICES,
        null=False,
        max_length=30,
        default=BuildingStatusModel.DEFAULT_STATUS,
    )
    # an event can modify several buildings at once
    # all the buildings modified by the same event will have the same event_id
    event_id = models.UUIDField(null=True, db_index=True)
    # the possible event types
    # creation: the building is created for the first time
    # update: some fields of an existing building are modified
    # deletion: the building is deleted, because it had no reason to be in the RNB in the first place
    # WARNING : a deletion is different from a real building demolition, which would be a change of the status (a thus an event_type: update).
    # merge: two or more buildings are merged into one
    # split: one building is split into two or more
    event_type = models.CharField(
        choices=[
            ("creation", "creation"),
            ("update", "update"),
            ("deletion", "deletion"),
            ("merge", "merge"),
            ("split", "split"),
        ],
        max_length=10,
        null=True,
    )
    # the user at the origin of the event
    event_user = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    # only currently active buildings are considered part of the RNB
    is_active = models.BooleanField(db_index=True, default=True)
    # this field is the source of truth for the building <> address link
    # it contains BAN ids (clé d'interopérabilité)
    addresses_id = ArrayField(models.CharField(max_length=40), null=True)

    class Meta:
        abstract = True


class BuildingAddressesReadOnly(models.Model):
    building = models.ForeignKey("Building", on_delete=models.CASCADE, db_index=True)
    address = models.ForeignKey("Address", on_delete=models.CASCADE, db_index=True)

    class Meta:
        unique_together = ("building", "address")


class Building(BuildingAbstract):
    # this only exists to make it possible for the Django ORM to access the associated addresses
    # but this field is read-only : you should not attempt to save a building/address association through this field
    # use addresses_id instead.
    addresses_read_only = models.ManyToManyField(
        "Address",
        blank=True,
        related_name="buildings_read_only",
        through="BuildingAddressesReadOnly",
    )

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

    class Meta:
        # ordering = ["rnb_id"]
        indexes = [
            GinIndex(fields=["event_origin"], name="bdg_event_origin_idx"),
            GinIndex(fields=["addresses_id"], name="bdg_addresses_id_idx"),
            models.Index(fields=("status",), name="bdg_status_idx"),
            GinIndex(fields=("ext_ids",), name="bdg_ext_ids_idx"),
            # lower is used to create an index on the start of the time range
            Index(Lower("sys_period"), name="bdg_sys_period_start_idx"),
            models.Index(fields=("event_type",), name="bdg_event_type_idx"),
        ]


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
        indexes = [
            GinIndex(fields=["event_origin"], name="bdg_history_event_origin_idx"),
            models.Index(fields=("status",), name="bdg_history_status_idx"),
            Index(Lower("sys_period"), name="bdg_hist_sys_period_start_idx"),
            models.Index(fields=("event_type",), name="bdg_history_event_type_idx"),
        ]


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
    achieved_at = models.DateField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    creator = models.ForeignKey(User, on_delete=models.PROTECT, null=True)

    class Meta:
        ordering = ["decided_at"]


class BuildingADS(models.Model):
    # building = models.ForeignKey(Building, on_delete=models.CASCADE)
    rnb_id = models.CharField(max_length=12, null=True)
    shape = models.GeometryField(null=True, srid=4326)
    ads = models.ForeignKey(
        ADS, related_name="buildings_operations", on_delete=models.CASCADE
    )

    operation = models.CharField(max_length=10, null=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("rnb_id", "ads")


class Candidate(models.Model):
    shape = models.GeometryField(null=True, srid=4326, spatial_index=False)
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

    inspected_at = models.DateTimeField(null=True, db_index=True)
    inspection_details = models.JSONField(null=True)
    created_by = models.JSONField(null=True)
    random = models.IntegerField(db_index=True, null=False, default=0)


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
    street_rep = models.CharField(max_length=100, null=True)
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


class Contribution(models.Model):
    id = models.AutoField(primary_key=True)
    rnb_id = models.CharField(max_length=255, null=True)
    text = models.TextField(null=True)
    email = models.EmailField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        choices=[("pending", "pending"), ("fixed", "fixed"), ("refused", "refused")],
        max_length=10,
        null=False,
        default="pending",
        db_index=True,
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(null=True, blank=True)
    review_user = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True
    )
