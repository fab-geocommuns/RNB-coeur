from batid.utils.misc import is_float
from batid.models import Building, BuildingStatus
from batid.services.bdg_status import BuildingStatus as BuildingStatusRef
from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.db.models import QuerySet


class BuildingSearch:
    MAX_HAUSDORFF_DISTANCE = 1.5

    def __init__(self):
        self.params = self.BuildingSearchParams()
        self.qs = None

    def set_params(self, **kwargs):
        self.params.set_filters(**kwargs)

    def set_params_from_url(self, **kwargs):
        self.params.set_filters_from_url(**kwargs)

    def get_queryset(self) -> QuerySet:
        # ###################
        # Filters
        # ###################

        wheres = []
        joins = []
        group_by = None
        params = {}

        # Bounding box
        if self.params.bb:
            wheres = ["ST_Intersects(point, %(bb)s)"]
            params["bb"] = f"{self.params.bb}"

        # Status
        if self.params.status:
            joins.append(
                f"LEFT JOIN {BuildingStatus._meta.db_table} as s ON s.building_id = b.id"
            )
            group_by = "b.id"

            wheres.append("s.type IN %(status)s AND s.is_current = TRUE")
            params["status"] = tuple(self.params.status)

        # Polygon
        if self.params.poly:
            wheres = ["ST_HausdorffDistance(shape, %(poly)s) <= %(max_hausdorff_dist)s"]
            params["poly"] = f"{self.params.poly}"
            params["max_hausdorff_dist"] = self.MAX_HAUSDORFF_DISTANCE

        # JOIN
        joins_str = ""
        if joins:
            joins_str = " ".join(joins)

        # WHERE
        where_str = ""
        if wheres:
            where_str = "WHERE " + " AND ".join(wheres)

        # GROUP BY
        group_by_str = ""
        if group_by:
            group_by_str = f"GROUP BY {group_by}"

        # ORBER BY
        order_str = ""
        if self.params.sort:
            order_str = f"ORDER BY {self.params.sort} ASC"

        query = f"SELECT b.id, b.rnb_id FROM {Building._meta.db_table} as b {joins_str} {where_str} {group_by_str} {order_str} LIMIT 10"

        qs = (
            Building.objects.raw(query, params)
            .prefetch_related("addresses")
            .prefetch_related("status")
        )

        # print("---- QUERY ---")
        # print(qs.query)

        return qs

    def is_valid(self):
        return self.params.is_valid()

    @property
    def errors(self):
        return self.params.errors

    class BuildingSearchParams:
        SORT_DEFAULT = "rnb_id"
        SORT_CHOICES = ["rnb_id"]

        PARAM_SPLITTER = ","

        def __init__(self, **kwargs):
            # ##########
            # Init properties
            # ##########

            # Filters
            self.bb = None
            self.status = []
            self.poly = None
            self.sort = None

            # Allowed status
            self.allowed_status = BuildingStatusRef.PUBLIC_TYPES_KEYS

            # Internals
            self.__errors = []

        def set_filters(self, **kwargs):
            if "bb" in kwargs:
                self.set_bb(kwargs["bb"])

            if "status" in kwargs:
                self.set_status(kwargs["status"])

            if "poly" in kwargs:
                self.set_poly(kwargs["poly"])

            if "sort" in kwargs:
                self.set_sort(kwargs["sort"])

        def set_filters_from_url(self, **kwargs):
            # ##########
            # Set up filters
            # ##########

            if "bb" in kwargs:
                self.set_bb_str(kwargs["bb"])

            if "status" in kwargs:
                self.set_status_str(kwargs["status"])

            # todo : poly
            # if "poly" in kwargs:
            #     self.set_poly_str(kwargs["poly"])

            if "sort" in kwargs:
                self.set_sort_str(kwargs["sort"])

        @property
        def errors(self):
            return self.__errors

        def is_valid(self) -> bool:
            return len(self.__errors) == 0

        def set_sort_str(self, sort_str: str) -> None:
            if sort_str is not None:
                self.set_sort(sort_str)

        def set_sort(self, sort: str) -> None:
            if self.__validate_sort(sort):
                self.sort = sort

        def __validate_sort(self, sort: str) -> bool:
            if sort not in self.SORT_CHOICES:
                self.__errors.append(
                    f"sort : sort parameter must be one of {self.SORT_CHOICES}"
                )
                return False

            return True

        def set_bb_str(self, bb_str: str) -> None:
            if bb_str is not None:
                if self.__validate_bb_str(bb_str):
                    bb = self.__convert_bb_str(bb_str)
                    self.set_bb(bb)

        def set_bb(self, bb) -> None:
            if self.__validate_bb(bb):
                self.bb = bb

        def __convert_bb_str(self, bb_str: str) -> Polygon:
            nw_lat, nw_lng, se_lat, se_lng = [
                float(coord) for coord in bb_str.split(self.PARAM_SPLITTER)
            ]

            poly_coords = (
                (nw_lng, nw_lat),
                (nw_lng, se_lat),
                (se_lng, se_lat),
                (se_lng, nw_lat),
                (nw_lng, nw_lat),
            )

            return Polygon(poly_coords, srid=4326).transform(
                settings.DEFAULT_SRID, clone=True
            )

        def __validate_bb_str(self, bb_str: str) -> bool:
            format_msg = "bb : bounding box parameter must be a string of 4 floats separated by a comma"

            if not bb_str:
                return False

            coords = bb_str.split(self.PARAM_SPLITTER)

            if len(coords) != 4:
                self.__errors.append(format_msg)
                return False

            for coord in coords:
                if not is_float(coord):
                    self.__errors.append(format_msg)
                    return False

            # Convert all params to floats and dispatch them to the right property
            nw_lat, nw_lng, se_lat, se_lng = [float(coord) for coord in coords]

            if nw_lat <= se_lat:
                self.__errors.append(
                    "bb : north-west latitude must be greater than south-east latitude"
                )
                return False

            if nw_lng >= se_lng:
                self.__errors.append(
                    "bb : south-east longitude must be greater than north-west longitude"
                )
                return False

            return True

        def __validate_bb(self, bb: Polygon) -> bool:
            if bb is None:
                return False

            # Error is srid is none
            if bb.srid is None:
                self.__errors.append("bb : bounding box must have a SRID")
                return False

            if not bb.valid:
                self.__errors.append(
                    f"bb : bounding box is not valid. Reason: {bb.valid_reason}"
                )
                return False

            return True

        def set_status_str(self, status_str: str) -> None:
            if status_str is not None:
                status = self.__convert_status_str(status_str)
                self.set_status(status)

        def set_status(self, status: list) -> None:
            if self.__validate_status(status):
                self.status = status

        def __validate_status(self, status: list) -> bool:
            for s in status:
                if s not in self.allowed_status:
                    self.__errors.append(
                        f'status : status "{s}" is invalid. Available status are: {BuildingStatusRef.TYPES}'
                    )
                    return False
            return True

        def __convert_status_str(self, status_str: str) -> list:
            if status_str == "all":
                return self.allowed_status
            return status_str.split(",")

        def set_poly(self, poly: Polygon) -> None:
            if poly is not None:
                if self.__validate_poly(poly):
                    self.poly = self.__convert_poly(poly)

        def __convert_poly(self, poly: Polygon) -> Polygon:
            if poly.srid == settings.DEFAULT_SRID:
                return poly

            return poly.transform(settings.DEFAULT_SRID, clone=True)

        def __validate_poly(self, poly: Polygon):
            if not isinstance(poly, Polygon):
                self.__errors.append("poly : polygon must be a Polygon object")
                return False

            if poly.srid is None:
                self.__errors.append("poly : polygon must have a SRID")
                return False

            if not poly.valid:
                self.__errors.append(
                    f"poly : polygon is not valid. Reason: {poly.valid_reason}"
                )
                return False

            return True
