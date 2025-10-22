import json
import uuid
from copy import deepcopy
from typing import Optional

from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.indexes import GistIndex
from django.db import transaction
from django.db.models import CheckConstraint
from django.db.models import F
from django.db.models import Func
from django.db.models import Q
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower
from django.db.models.indexes import Index

from .others import Address
from .others import Contribution
from .others import SummerChallenge
from api_alpha.typeddict import SplitCreatedBuilding
from batid.exceptions import NotEnoughBuildings
from batid.exceptions import OperationOnInactiveBuilding
from batid.exceptions import RevertNotAllowed
from batid.services.bdg_status import BuildingStatus as BuildingStatusModel
from batid.services.rnb_id import generate_rnb_id
from batid.utils.db import from_now_to_infinity
from batid.utils.geo import assert_shape_is_valid
from batid.validators import validate_one_ext_id


class BuildingAbstract(models.Model):
    rnb_id = models.CharField(max_length=12, null=False, unique=True, db_index=True)  # type: ignore[var-annotated]
    point = models.PointField(null=True, spatial_index=True, srid=4326)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]
    shape = models.GeometryField(null=True, spatial_index=True, srid=4326)  # type: ignore[var-annotated]
    ext_ids = models.JSONField(null=True)
    event_origin = models.JSONField(null=True)
    # temporal table field
    sys_period = DateTimeRangeField(null=False, default=from_now_to_infinity)
    # in case of building merge, we want in the future to keep the list of the parent buildings
    # not implemented for now
    parent_buildings = models.JSONField(null=True)
    # enum field for the building status
    status = models.CharField(  # type: ignore[var-annotated]
        choices=BuildingStatusModel.TYPES_CHOICES,
        null=False,
        max_length=30,
        default=BuildingStatusModel.DEFAULT_STATUS,
    )
    # an event can modify several buildings at once
    # all the buildings modified by the same event will have the same event_id
    event_id = models.UUIDField(null=True, db_index=True)  # type: ignore[var-annotated]
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
        "revert_update",
        "deactivation",
        "reactivation",
        "merge",
        "revert_merge",
        "split",
        "revert_split",
    ]
    event_type = models.CharField(  # type: ignore[var-annotated]
        choices=[(e, e) for e in EVENT_TYPES],
        max_length=13,
        null=True,
    )
    # the user at the origin of the event
    event_user = models.ForeignKey(User, on_delete=models.PROTECT, null=True)  # type: ignore[var-annotated]
    # in case of a revert operation, the event_id of the reverted event
    revert_event_id = models.UUIDField(null=True)
    # only currently active buildings are considered part of the RNB
    is_active = models.BooleanField(db_index=True, default=True)  # type: ignore[var-annotated]
    # this field is the source of truth for the building <> address link
    # it contains BAN ids (clé d'interopérabilité)
    addresses_id = ArrayField(models.CharField(max_length=40), null=True)  # type: ignore[var-annotated]

    class Meta:
        abstract = True


class PGPoint(Func):
    function = "point"
    template = "%(function)s(%(expressions)s)"
    output_field = models.Field()


class Building(BuildingAbstract):
    # this only exists to make it possible for the Django ORM to access the associated addresses
    # but this field is read-only : you should not attempt to save a building/address association through this field
    # use addresses_id instead.
    addresses_read_only = models.ManyToManyField(  # type: ignore[var-annotated]
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
            raise OperationOnInactiveBuilding(
                f"Impossible de désactiver un identifiant déjà inactif : {self.rnb_id}"
            )

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
            raise RevertNotAllowed()

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
            (status is None or status == self.status)
            and (
                addresses_id is None
                or set(addresses_id) == set(self.addresses_id or [])
            )
            and (ext_ids is None or ext_ids == self.ext_ids)
            and (shape is None or shape == self.shape)
        ):
            # let's do nothing
            return

        if not self.is_active:
            raise OperationOnInactiveBuilding(
                f"Impossible de mettre à jour un identifiant inactif : {self.rnb_id}"
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

        # we don't want to directly modify existing_ext_ids
        # in case it is a reference to the object ext_ids
        existing_ext_ids = deepcopy(existing_ext_ids)

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
            raise NotEnoughBuildings()

        if any([not building.is_active for building in buildings]):
            raise OperationOnInactiveBuilding(
                "Impossible de fusionner des identifiants inactifs"
            )

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
    @staticmethod
    def revert_merge(
        user: User,
        event_origin: dict,
        event_id_to_revert: uuid.UUID,
    ) -> uuid.UUID:
        # get id of all buildings to revert
        buildings_to_revert = list(
            Building.objects.all()
            .filter(event_id=event_id_to_revert)
            .order_by("rnb_id")
        )
        buildings_checking = list(
            BuildingWithHistory.objects.all()
            .filter(event_id=event_id_to_revert)
            .order_by("rnb_id")
        )

        # Only the last version of a Building is in the Building table.
        # As soon as it is modified, that version is transfered in the History table.
        # After a merge, all the buildings linked to the merge live in the Building table.
        # Comparing Building and BuildingWithHistory is a simple way to check no building has been touched since the merge.
        if [b.id for b in buildings_to_revert] != [b.id for b in buildings_checking]:
            raise RevertNotAllowed()

        # should not happen
        if len(buildings_to_revert) < 3:
            raise NotEnoughBuildings()

        deactivated_buildings = [b for b in buildings_to_revert if not b.is_active]
        created_buildings = [b for b in buildings_to_revert if b.is_active]

        if len(created_buildings) != 1:
            raise RevertNotAllowed()
        created_building = created_buildings[0]

        new_event_id = uuid.uuid4()

        for building in deactivated_buildings:
            building.is_active = True
            building.event_type = "revert_merge"
            building.event_id = new_event_id
            building.event_user = user
            building.event_origin = event_origin
            building.revert_event_id = event_id_to_revert
            building.save()

        created_building.is_active = False
        created_building.event_type = "revert_merge"
        created_building.event_id = new_event_id
        created_building.event_user = user
        created_building.event_origin = event_origin
        created_building.revert_event_id = event_id_to_revert
        created_building.save()

        return new_event_id

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
                f"Impossible de diviser un identifiant inactif : {self.rnb_id}"
            )

        if not isinstance(created_buildings, list) or len(created_buildings) < 2:
            raise NotEnoughBuildings()

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
            # this index is a bit strange for performance reasons
            # we need to write queries that filter both on point (geometry) and on the building id
            # queries look like point && bbox and id > XXX
            # treating the id as a geographical point (point(id, 0)) allows us to create a gist index
            # on both point and id columns.
            # queries can be written like point && bbox AND point(id,0) >> point(XXX, 0) order by point(id, 0) <-> point(XXX, 0)
            # tests with the btree_gist extension have been disapointing, so we ended up using this solution.
            GistIndex(
                F("point"),
                PGPoint(F("id"), 0),
                name="bdg_point_id_gist_idx",
            ),
        ]
        constraints = [
            # a DB level constraint on the authorized values for the event_type columns
            CheckConstraint(
                check=Q(event_type__in=BuildingAbstract.EVENT_TYPES),
                name="valid_event_type_check",
            ),
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
    bh_id = models.BigAutoField(  # type: ignore[var-annotated]
        auto_created=True, primary_key=True, serialize=False, verbose_name="BH_ID"
    )
    # primary key coming from the Building table, but not unique here.
    id = models.BigIntegerField()  # type: ignore[var-annotated]
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

        constraints = [
            # verify the couple rnb_id/event_id is unique
            UniqueConstraint(
                fields=["rnb_id", "event_id"],
                name="unique_rnb_id_event_id",
            )
        ]
