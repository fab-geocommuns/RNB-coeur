import json
import uuid
from datetime import datetime
from typing import Optional

import requests
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.indexes import GinIndex
from django.db import transaction
from django.db.models import CheckConstraint
from django.db.models import Q
from django.db.models.functions import Lower
from django.db.models.indexes import Index

from api_alpha.typeddict import SplitCreatedBuilding
from batid.exceptions import BANAPIDown
from batid.exceptions import BANBadRequest
from batid.exceptions import BANBadResultType
from batid.exceptions import BANUnknownCleInterop
from batid.exceptions import NotEnoughBuildings
from batid.exceptions import OperationOnInactiveBuilding
from batid.services.bdg_status import BuildingStatus as BuildingStatusModel
from batid.services.rnb_id import generate_rnb_id
from batid.utils.db import from_now_to_infinity
from batid.utils.geo import assert_shape_is_valid
from batid.validators import JSONSchemaValidator
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
    # deactivation: the rnb id is deactivated, because the corresponding building had no reason to be in the RNB in the first place
    # WARNING : a deactivation is different from a real building demolition, which would be a change of the status (a thus an event_type: update).
    # merge: two or more buildings are merged into one
    # split: one building is split into two or more
    EVENT_TYPES = [
        "creation",
        "update",
        "deactivation",
        "reactivation",
        "merge",
        "split",
    ]
    event_type = models.CharField(
        choices=[(e, e) for e in EVENT_TYPES],
        max_length=12,
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

    def shape_geojson(self):
        if not self.shape:
            return None

        # todo : is there a better way to go from a GeometryField to geojson dict ?
        # We are doing points > dict > json str > dict. It is inefficient.
        return json.loads(self.shape.transform(4326, clone=True).geojson)

    def ads_geojson(self):
        return json.loads(self.point.transform(4326, clone=True).geojson)

    def point_lat(self):
        return self.point_geojson()["coordinates"][1]

    def point_lng(self):
        return self.point_geojson()["coordinates"][0]

    @transaction.atomic
    def deactivate(self, user: User, event_origin):
        """
        IMPORTANT NOTICE: this method must only be used in the case the building was never meant to be in the RNB.
        eg: some trees were visually considered as a building and added to the RNB.
        ----
        It is not expected to delete anything in the RNB, as it would break our capacity to audit its history.
        This deactivate method is used to mark a RNB_ID as inactive, with an associated event_type "deactivation"
        """
        if self.is_active:
            event_id = uuid.uuid4()
            self.event_type = "deactivation"
            self.is_active = False
            self.event_id = event_id
            self.event_user = user
            self.event_origin = event_origin
            self.save()

            SummerChallenge.score_deactivation(
                user, self.point, self.rnb_id, self.event_id
            )

            except_for_this_contribution = get_contribution_id_from_event_origin(
                event_origin
            )

            self._refuse_pending_contributions(
                user, event_id, except_for_this_contribution
            )
        else:
            print(f"Cannot deactivate an inactive building: {self.rnb_id}")

    @transaction.atomic
    def reactivate(self, user: User, event_origin):
        """
        This method allows a user to undo a RNB ID deactivation made by mistake.
        We may add some checks in the future, like only allowing to reactivate a recently deactivated ID.
        """
        if self.is_active == False and self.event_type == "deactivation":
            previous_event_id = self.event_id

            self.event_type = "reactivation"
            self.is_active = True
            self.event_id = uuid.uuid4()
            self.event_user = user
            self.event_origin = event_origin
            self.save()

            self._reset_linked_contributions(user, previous_event_id)
        else:
            print(
                f"Cannot reactivate RNB ID : {self.rnb_id}. Can only reactivate a previously deactivated RNB ID."
            )

    @transaction.atomic
    def update(
        self,
        user: User | None,
        event_origin: dict | None,
        status: str | None,
        addresses_id: list | None,
        ext_ids: list | None = None,
        shape: GEOSGeometry | None = None,
    ):
        if (
            status is None
            and addresses_id is None
            and ext_ids is None
            and shape is None
        ):

            raise Exception("Missing data to update the building")

        if not self.is_active:
            raise OperationOnInactiveBuilding(
                f"Cannot update inactive building {self.rnb_id}"
            )
        if shape:
            assert_shape_is_valid(shape)

        self.event_type = "update"
        self.event_id = uuid.uuid4()
        self.event_user = user
        self.event_origin = event_origin

        if status is not None and self.status != status:
            self.status = status
            SummerChallenge.score_status(user, self.point, self.rnb_id, self.event_id)

        if ext_ids is not None:
            self.ext_ids = ext_ids

        if shape is not None and self.shape != shape:
            self.shape = shape
            self.point = shape.point_on_surface
            # Summer Challenge!
            SummerChallenge.score_shape(user, self.point, self.rnb_id, self.event_id)

        if addresses_id is not None:
            Address.add_addresses_to_db_if_needed(addresses_id)

            # Summer Challenge!
            if self.addresses_id != addresses_id:
                SummerChallenge.score_address(
                    user, self.point, self.rnb_id, self.event_id
                )

            self.addresses_id = addresses_id

        self.save()

    def _refuse_pending_contributions(
        self, user: User, event_id, except_for_this_contribution_id=None
    ):

        msg = f"Ce signalement a été refusé suite à la désactivation du bâtiment {self.rnb_id}."
        contributions = Contribution.objects.filter(
            rnb_id=self.rnb_id, status="pending", report=True
        )

        if except_for_this_contribution_id:
            # you may want to refuse all contributions, except for the one being currently treated
            contributions = contributions.exclude(id=except_for_this_contribution_id)

        for c in contributions:
            c.refuse(user, msg, status_updated_by_event_id=event_id)

    def _reset_linked_contributions(self, user: User, event_id):
        contributions = Contribution.objects.filter(status_updated_by_event_id=event_id)
        for c in contributions:
            c.reset_pending()

    @staticmethod
    def add_ext_id(
        existing_ext_ids: list | None,
        source: str,
        source_version: Optional[str],
        id: str,
        created_at: str,
    ) -> list[dict]:
        ext_id = {
            "source": source,
            "source_version": source_version,
            "id": id,
            "created_at": created_at,
        }

        validate_one_ext_id(ext_id)

        if not existing_ext_ids:
            existing_ext_ids = []

        existing_ext_ids.append(ext_id)
        new_ext_ids = sorted(existing_ext_ids, key=lambda k: k["created_at"])
        return new_ext_ids

    @staticmethod
    @transaction.atomic
    def create_new(
        user: User | None,
        event_origin: dict | None,
        status: str,
        addresses_id: list,
        shape: GEOSGeometry,
        ext_ids: list,
    ):
        if (
            not event_origin
            or not status
            or addresses_id is None
            or not shape
            or ext_ids is None
        ):
            raise Exception("Missing information to create a new building")

        assert_shape_is_valid(shape)

        point = shape if shape.geom_type == "Point" else shape.point_on_surface
        rnb_id = generate_rnb_id()
        event_id = uuid.uuid4()

        # Summer Challenge!
        SummerChallenge.score_creation(user, point, rnb_id, event_id)

        if addresses_id is not None and len(addresses_id) > 0:
            Address.add_addresses_to_db_if_needed(addresses_id)

            # Summer Challenge!
            SummerChallenge.score_address(user, point, rnb_id, event_id)

        return Building.objects.create(
            rnb_id=rnb_id,
            point=point,
            shape=shape,
            ext_ids=ext_ids,
            event_origin=event_origin,
            status=status,
            event_id=event_id,
            event_type="creation",
            event_user=user,
            is_active=True,
            addresses_id=addresses_id,
        )

    @staticmethod
    @transaction.atomic
    def merge(buildings: list, user, event_origin, status, addresses_id):
        from batid.utils.geo import merge_contiguous_shapes

        if not isinstance(buildings, list) or len(buildings) < 2:
            raise NotEnoughBuildings("Not enough buildings to merge.")

        if any([not building.is_active for building in buildings]):
            raise OperationOnInactiveBuilding("Cannot merge inactive buildings.")

        event_id = uuid.uuid4()
        parent_buildings = [building.rnb_id for building in buildings]
        merged_shape = merge_contiguous_shapes(
            [GEOSGeometry(building.shape) for building in buildings if building.shape]
        )
        merged_ext_ids = [
            ext_id for building in buildings for ext_id in building.ext_ids or []
        ]
        # remove eventual duplicates
        merged_ext_ids = [
            ext_id
            for i, ext_id in enumerate(merged_ext_ids)
            if ext_id not in merged_ext_ids[i + 1 :]
        ]

        if addresses_id is not None:
            Address.add_addresses_to_db_if_needed(addresses_id)

        except_for_this_contribution = get_contribution_id_from_event_origin(
            event_origin
        )

        def remove_existing_builing(building):
            building.is_active = False
            building.event_type = "merge"
            building.event_id = event_id
            building.event_user = user
            building.event_origin = event_origin
            building.save()
            building._refuse_pending_contributions(
                user, event_id, except_for_this_contribution
            )

        for building in buildings:
            remove_existing_builing(building)

        # Create the new merged building
        building = Building()
        building.rnb_id = generate_rnb_id()
        building.status = status
        building.is_active = True
        building.event_type = "merge"
        building.event_id = event_id
        building.event_user = user
        building.event_origin = event_origin
        building.parent_buildings = parent_buildings
        building.addresses_id = addresses_id
        building.shape = merged_shape
        building.point = merged_shape.point_on_surface
        building.ext_ids = merged_ext_ids
        building.save()

        SummerChallenge.score_merge(user, building.point, building.rnb_id, event_id)

        return building

    @transaction.atomic
    def split(
        self,
        created_buildings: list[SplitCreatedBuilding],
        user: User,
        event_origin: dict,
    ):
        if not event_origin or not user:
            raise Exception("Missing information to split the building")

        if not self.is_active:
            raise OperationOnInactiveBuilding(
                f"Cannot split inactive building {self.rnb_id}"
            )

        if not isinstance(created_buildings, list) or len(created_buildings) < 2:
            raise NotEnoughBuildings("A building must be split at least in two")

        event_id = uuid.uuid4()

        # deactivate the parent building
        self.is_active = False
        self.event_type = "split"
        self.event_id = event_id
        self.event_user = user
        self.event_origin = event_origin
        self.save()

        def create_child_building(
            status: str, addresses_cle_interop: list[str], shape: str
        ):
            addresses_cle_interop = list(set(addresses_cle_interop))
            if addresses_cle_interop is not None:
                Address.add_addresses_to_db_if_needed(addresses_cle_interop)
            geos_shape = GEOSGeometry(shape)
            assert_shape_is_valid(geos_shape)

            child_building = Building()
            child_building.rnb_id = generate_rnb_id()
            child_building.status = status
            child_building.is_active = True
            child_building.event_type = "split"
            child_building.event_id = event_id
            child_building.event_user = user
            child_building.event_origin = event_origin
            child_building.parent_buildings = [self.rnb_id]
            child_building.addresses_id = addresses_cle_interop
            child_building.shape = geos_shape
            child_building.point = geos_shape.point_on_surface
            child_building.ext_ids = self.ext_ids
            child_building.save()

            return child_building

        child_buildings = []

        for building_info in created_buildings:
            status = building_info["status"]
            addresses_cle_interop = building_info["addresses_cle_interop"]
            shape = building_info["shape"]
            child_buildings.append(
                create_child_building(status, addresses_cle_interop, shape)
            )

        SummerChallenge.score_split(user, self.point, self.rnb_id, event_id)

        return child_buildings

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
            GinIndex(fields=["parent_buildings"], name="bdg_parent_buildings_idx"),
            models.Index(
                fields=(
                    "is_active",
                    "status",
                ),
                name="batid_building_active_status",
            ),
        ]
        constraints = [
            # a DB level constraint on the authorized values for the event_type columns
            CheckConstraint(
                check=Q(event_type__in=BuildingAbstract.EVENT_TYPES),
                name="valid_event_type_check",
            )
        ]


def get_contribution_id_from_event_origin(event_origin):
    return (
        event_origin.get("contribution_id")
        if isinstance(event_origin, dict)
        and event_origin.get("source") == "contribution"
        else None
    )


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
            GinIndex(fields=["parent_buildings"], name="bdg_hist_parent_buildings_idx"),
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


class Department_subdivided(models.Model):
    # this model exists for performance reasons
    # it is much faster to query on the shape of a department if it is subdivided
    code = models.CharField(max_length=3, null=False)
    name = models.CharField(max_length=200, null=False)
    shape = models.PolygonField(null=True, spatial_index=True, srid=4326)


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
        verbose_name = "ADS"
        verbose_name_plural = "ADS"


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

    source_version = models.CharField(max_length=20, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Address(models.Model):
    id = models.CharField(max_length=40, primary_key=True, db_index=True)
    source = models.CharField(max_length=10, null=False)  # BAN or other origin
    point = models.PointField(null=True, spatial_index=True, srid=4326)
    street_number = models.CharField(max_length=10, null=True)
    street_rep = models.CharField(max_length=100, null=True)
    street = models.CharField(max_length=200, null=True)
    city_name = models.CharField(max_length=100, null=True)
    city_zipcode = models.CharField(max_length=5, null=True)
    city_insee_code = models.CharField(max_length=5, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    def add_addresses_to_db_if_needed(addresses_id):
        """given a list of "clés d'interopérabilité BAN", we add those addresses to our Address table if they don't exist yet."""
        for address_id in addresses_id:
            Address.add_address_to_db_if_needed(address_id)

    @staticmethod
    def add_address_to_db_if_needed(address_id):
        if Address.objects.filter(id=address_id).exists():
            return
        else:
            Address.add_new_address_from_ban_api(address_id)

    @staticmethod
    def add_new_address_from_ban_api(address_id):

        BAN_API_URL = "https://plateforme.adresse.data.gouv.fr/lookup/"

        url = f"{BAN_API_URL}{address_id}"
        r = requests.get(url)

        if r.status_code == 200:
            data = r.json()
            Address.save_new_address(data)
        elif r.status_code == 404:
            raise BANUnknownCleInterop
        elif r.status_code == 400:
            raise BANBadRequest
        else:
            raise BANAPIDown

    @staticmethod
    def save_new_address(data):
        if data["type"] != "numero":
            raise BANBadResultType

        Address.objects.create(
            id=data["cleInterop"],
            source="ban",
            point=f'POINT ({data["lon"]} {data["lat"]})',
            street_number=data["numero"],
            street_rep=data["suffixe"],
            street=data["voie"]["nomVoie"],
            city_name=data["commune"]["nom"],
            city_zipcode=data["codePostal"],
            city_insee_code=data["commune"]["code"],
        )


class Organization(models.Model):
    name = models.CharField(max_length=100, null=False)
    users = models.ManyToManyField(User, related_name="organizations")
    managed_cities = ArrayField(models.CharField(max_length=6), null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    job_title = models.CharField(max_length=255, blank=True, null=True)


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
    # is it a user report (a modification proposal or "signalement" in French) or a direct data modification?
    report = models.BooleanField(null=False, db_index=True, default=True)
    # useful for reports (signalements)
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
    # if an event on a Building (eg a deactivation) updates the status of a "signalement" (eg status set to refused).
    status_updated_by_event_id = models.UUIDField(null=True, db_index=True)

    def fix(self, user, review_comment=""):
        if self.status != "pending":
            raise ValueError("Contribution is not pending.")

        self.status = "fixed"
        self.status_changed_at = datetime.now()
        self.review_comment = review_comment
        self.review_user = user
        self.save()

    def refuse(self, user, review_comment="", status_updated_by_event_id=None):
        if self.status != "pending":
            raise ValueError("Contribution is not pending.")

        self.status = "refused"
        self.status_changed_at = datetime.now()
        self.review_comment = review_comment
        self.review_user = user
        self.status_updated_by_event_id = status_updated_by_event_id
        self.save()

    def reset_pending(self):
        """
        A signalement has been refused because its underlying building has been deactivated.
        The building is finally reactivated => we reset the signalement to a pending status.
        """
        self.status = "pending"
        self.status_changed_at = None
        self.review_comment = None
        self.review_user = None
        self.status_updated_by_event_id = None
        self.save()


class DataFix(models.Model):
    """
    Sometimes we need to fix the data in the RNB.
    We identify a problem, run queries to find the corresponding buildings
    and then fix them.
    """

    # a message explaining the problem and the associated fix
    # the text will be displayed to our users
    # and should be written in French.
    # ex : "Suppression des bâtiments légers importés par erreur"
    text = models.TextField(null=True)
    # the user who created the fix
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)


DIFFUSION_DATABASE_ATTRIBUTES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
            },
            "description": {
                "type": "string",
            },
        },
        "required": ["name", "description"],
        "additionalProperties": False,
    },
}


class DiffusionDatabase(models.Model):
    display_order = models.FloatField(null=False, default=0)
    name = models.CharField(max_length=255)
    documentation_url = models.URLField(null=True)
    publisher = models.CharField(max_length=255, null=True)
    licence = models.CharField(max_length=255, null=True)
    tags = ArrayField(
        models.CharField(max_length=255), null=False, default=list, blank=True
    )
    description = models.TextField(blank=True)
    image_url = models.URLField(null=True)
    is_featured = models.BooleanField(default=False)
    featured_summary = models.TextField(blank=True)
    attributes = models.JSONField(
        null=False,
        default=list,
        blank=True,
        validators=[JSONSchemaValidator(DIFFUSION_DATABASE_ATTRIBUTES_SCHEMA)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class KPI(models.Model):
    name = models.CharField(max_length=255, null=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    value = models.FloatField(null=False)
    value_date = models.DateField(null=True)

    class Meta:
        ordering = ["value_date"]
        unique_together = ("name", "value_date")


class SummerChallenge(models.Model):
    score = models.IntegerField(null=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=False, db_index=True)
    rnb_id = models.CharField(max_length=12, null=False, db_index=True)

    ACTIONS = [
        "update_address",
        "update_shape",
        "update_status",
        "creation",
        "merge",
        "split",
        "deactivation",
    ]
    action = models.CharField(
        choices=[(e, e) for e in ACTIONS], max_length=14, null=False, db_index=True
    )
    city = models.ForeignKey(City, on_delete=models.PROTECT, null=True, db_index=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, null=True, db_index=True
    )
    event_id = models.UUIDField(null=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    def get_dpt(point):
        d = Department_subdivided.objects.filter(shape__intersects=point).first()
        return Department.objects.filter(code=d.code).first() if d else None

    @staticmethod
    def get_city(point):
        return City.objects.filter(shape__intersects=point).first()

    @staticmethod
    def get_areas(point):
        if point:
            return (SummerChallenge.get_city(point), SummerChallenge.get_dpt(point))
        else:
            return (None, None)

    @staticmethod
    def score_address(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=3,
                user=user,
                action="update_address",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_creation(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=2,
                user=user,
                action="creation",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_shape(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=1,
                user=user,
                action="update_shape",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_status(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=1,
                user=user,
                action="update_status",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_deactivation(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=1,
                user=user,
                action="deactivation",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_split(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=1,
                user=user,
                action="split",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_merge(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=1,
                user=user,
                action="merge",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()
