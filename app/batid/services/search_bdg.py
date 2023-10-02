from batid.services.rnb_id import clean_rnb_id
from batid.utils.misc import is_float
from batid.models import Building, BuildingStatus, City, Plot
from batid.services.bdg_status import BuildingStatus as BuildingStatusRef
from batid.services.ban import BanFetcher
from django.conf import settings
from django.contrib.gis.geos import Polygon, MultiPolygon, Point
from django.db.models import QuerySet


class BuildingSearch:
    MAX_HAUSDORFF_DISTANCE = 4  # This value must be precised with a test set

    def __init__(self):
        self.params = self.BuildingSearchParams()
        self.qs = None
        self.scores = {}

    def set_params(self, **kwargs):
        self.params.set_filters(**kwargs)

    def set_params_from_url(self, **kwargs):
        self.params.set_filters_from_url(**kwargs)

    def get_queryset(self) -> QuerySet:
        self.prepare_params()

        # ###################
        # Filters
        # ###################

        selects = ["b.id", "b.rnb_id"]
        wheres = []
        joins = []
        group_by = None
        params = {}
        self.scores = {}

        # Bounding box
        if self.params.bb:
            wheres = ["ST_Intersects(point, %(bb)s)"]
            params["bb"] = f"{self.params.bb}"

        # RNB ID
        if self.params.rnb_id:
            wheres.append("rnb_id = %(rnb_id)s")
            params["rnb_id"] = self.params.rnb_id

        # Status
        if self.params.status:
            joins.append(
                f"LEFT JOIN {BuildingStatus._meta.db_table} as s ON s.building_id = b.id"
            )
            group_by = "b.id"

            wheres.append("s.type IN %(status)s AND s.is_current = TRUE")
            params["status"] = tuple(self.params.status)

        # #########################################
        # BAN ID
        if self.params._ban_id:
            joins.append(
                f"LEFT JOIN {Building.addresses.through._meta.db_table} as b_rel_a ON b_rel_a.building_id = b.id"
            )

            group_by = "b.id"

            self.scores[
                "ban_id_shared"
            ] = f"CASE WHEN %(ban_id)s = ANY(array_agg(b_rel_a.address_id)) THEN 1 ELSE 0 END"
            params["ban_id"] = self.params._ban_id

        # #########################################
        # Address point
        if self.params._ban_point:
            # Those scores and filters are almost similar to the ones used on the point params

            # ON THIS SIDE OF THE ROAD SCORE
            # We give more score (2 points) when point comes from BAN than from query
            # todo : if we have both point and address, we should use the same cluster for both
            cluster_q = f"SELECT c.cluster FROM (SELECT ST_UnaryUnion(unnest(ST_ClusterIntersecting(shape))) as cluster FROM {Plot._meta.db_table} WHERE ST_DWithin(shape, %(ban_point)s, 300)) c ORDER BY ST_Distance(c.cluster, %(ban_point)s) ASC LIMIT 1"
            self.scores[
                "ban_point_plot_cluster"
            ] = f"CASE WHEN ST_Intersects(shape, ({cluster_q})) THEN 2 ELSE 0 END"

            # DISTANCE TO THE POINT SCORE
            # We want to keep buildings that are close to the point
            # todo : does the double ST_Distance evaluation is a performance problem ?
            self.scores[
                "ban_point_distance"
            ] = f"CASE WHEN ST_Distance(shape, %(ban_point)s) > 0 THEN 2 / ST_Distance(shape, %(ban_point)s) ELSE 5 END"

            # Add the point to the params
            params["ban_point"] = f"{self.params._ban_point}"

        # #########################################
        # Point

        if self.params.point:
            self.params.point.transform(settings.DEFAULT_SRID)

            # ON THIS SIDE OF THE ROAD SCORE
            # Points tend to be on the right side of the road. We can filter out buildings that are on the other side of the road.
            # Public roads are not in cadastre plots. By grouping contiguous plots we can recreate simili-roads and keep only buildings intersecting this plot group.
            # todo : it might be interesting to pre-calculate cluster and store them in DB. It would be faster.
            cluster_q = f"SELECT c.cluster FROM (SELECT ST_UnaryUnion(unnest(ST_ClusterIntersecting(shape))) as cluster FROM {Plot._meta.db_table} WHERE ST_DWithin(shape, %(point)s, 300)) c ORDER BY ST_Distance(c.cluster, %(point)s) ASC LIMIT 1"
            self.scores[
                "point_plot_cluster"
            ] = f"CASE WHEN ST_Intersects(shape, ({cluster_q})) THEN 1 ELSE 0 END"

            # DISTANCE TO THE POINT SCORE
            # We want to keep buildings that are close to the point
            # todo : does the double ST_Distance evaluation is a performance problem ?
            self.scores[
                "point_distance"
            ] = f"CASE WHEN ST_Distance(shape, %(point)s) > 0 THEN 1 / ST_Distance(shape, %(point)s) ELSE 5 END"

            # LIMIT THE DISTANCE TO THE POINT
            wheres.append(f"ST_DWithin(shape, %(point)s, 400)")

            # Add the point to the params
            params["point"] = f"{self.params.point}"

        # #########################################
        # Restrict research in a radius around point and address point

        ban_point_where = "ST_DWithin(shape, %(ban_point)s, 400)"
        point_where = "ST_DWithin(shape, %(point)s, 400)"

        if self.params.point and self.params._ban_point:
            wheres.append(f"({ban_point_where} or {point_where})")
        elif self.params.point:
            wheres.append(point_where)
        elif self.params._ban_point:
            wheres.append(ban_point_where)

        # Polygon
        if self.params.poly:
            wheres = ["ST_HausdorffDistance(shape, %(poly)s) <= %(max_hausdorff_dist)s"]
            params["poly"] = f"{self.params.poly}"
            params["max_hausdorff_dist"] = self.MAX_HAUSDORFF_DISTANCE

        # City poly
        if self.params._city_poly:
            wheres = ["ST_Intersects(b.point, %(city_poly)s)"]
            params["city_poly"] = f"{self.params._city_poly}"

        # SELECT

        selects.append(
            "ST_AsEWKB(b.point) as point",
        )  # geometries must be sent back as EWKB to work with RawQuerySet
        select_str = ", ".join(selects)

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

        # PAGINATION
        pagination_str = ""
        if self.params.page:
            limit = 20
            offset = (self.params.page - 1) * limit

            pagination_str = f"LIMIT {limit} OFFSET {offset}"

        # SCORE CASES
        score_cases_str = ""
        if len(self.scores):
            score_cases_str = ", " + self.__each_score_case_str(self.scores)

        # SCORE SUM
        scores_sum = ", 0 as score"
        if len(self.scores):
            scores_sum = (
                ", "
                + " + ".join(self.scores.keys())
                + " as score, "
                + ", ".join(self.scores.keys())
            )

        # ######################
        # Assembling the queries

        score_query = (
            f"SELECT {select_str} {score_cases_str} "
            f"FROM {Building._meta.db_table} as b {joins_str} "
            f"{where_str} {group_by_str} {order_str}"
        )

        global_query = (
            f"WITH scored_bdgs AS ({score_query}) "
            f"SELECT *  {scores_sum} "
            f"FROM scored_bdgs "
            "ORDER BY score DESC "
            f"{pagination_str}"
        )

        qs = (
            Building.objects.raw(global_query, params)
            .prefetch_related("addresses")
            .prefetch_related("status")
        )

        # print("---- QUERY ---")
        # print(qs.query)

        return qs

    def prepare_params(self):
        self.params.prepare_params()

    def is_valid(self):
        return self.params.is_valid()

    @property
    def errors(self):
        return self.params.errors

    def __each_score_case_str(self, scores_dict):
        all = []

        for name, rule in scores_dict.items():
            all.append(f"{rule} AS {name}")

        return ", ".join(all)

    # Allow to override the BanFetcher class, for mocking it in tests
    def set_ban_fetcher_cls(self, cls):
        self.params.set_ban_fetcher_cls = cls

    class BuildingSearchParams:
        SORT_DEFAULT = "rnb_id"
        SORT_CHOICES = ["rnb_id"]

        PARAM_SPLITTER = ","

        def __init__(self, **kwargs):
            # ##########
            # Init properties
            # ##########

            # Filters
            self.rnb_id = None
            self.bb = None
            self.status = []
            self.point = None  # Can be any SRID
            self.address = None
            self.poly = None
            self.point = None
            self.sort = None
            self.insee_code = None
            self.name = None

            # Filters constructed from other filters
            # They can not be set directly
            self._city_poly = None

            self._osm_point = None

            self._ban_point = None
            self._ban_id = None

            # Pagination
            self.page = 1

            # Allowed status
            self.allowed_status = BuildingStatusRef.PUBLIC_TYPES_KEYS

            # Internals
            self.__errors = []
            self.__banFetcherCls = BanFetcher

        def set_filters(self, **kwargs):
            if "name" in kwargs:
                self.set_name(kwargs["name"])

            if "rnb_id" in kwargs:
                self.set_rnb_id(kwargs["rnb_id"])

            if "bb" in kwargs:
                self.set_bb(kwargs["bb"])

            if "status" in kwargs:
                self.set_status(kwargs["status"])

            if "poly" in kwargs:
                self.set_poly(kwargs["poly"])

            if "point" in kwargs:
                self.set_point(kwargs["point"])
            #
            if "address" in kwargs:
                self.set_address(kwargs["address"])

            if "sort" in kwargs:
                self.set_sort(kwargs["sort"])

            if "insee_code" in kwargs:
                self.set_insee_code(kwargs["insee_code"])

            if "page" in kwargs:
                self.set_page(kwargs["page"])

        def set_filters_from_url(self, **kwargs):
            # ##########
            # Set up filters
            # ##########

            if "rnb_id" in kwargs:
                self.set_rnb_id_from_url(kwargs["rnb_id"])

            if "bb" in kwargs:
                self.set_bb_from_url(kwargs["bb"])

            if "status" in kwargs:
                self.set_status_from_url(kwargs["status"])

            # todo : poly (for now it is not used in the url)
            # if "poly" in kwargs:
            #     self.set_poly_str(kwargs["poly"])

            if "point" in kwargs:
                self.set_point_from_url(kwargs["point"])
            #
            if "address" in kwargs:
                self.set_address_from_url(kwargs["address"])

            if "sort" in kwargs:
                self.set_sort_from_url(kwargs["sort"])

            if "insee_code" in kwargs:
                self.set_insee_code_from_url(kwargs["insee_code"])

            if "page" in kwargs:
                self.set_page_from_url(kwargs["page"])

        def set_ban_fetcher_cls(self, cls):
            self.__banFetcherCls = cls

        def prepare_params(self):
            self.prepare_address()
            self.prepare_point()  # Point preparation must be done after address preparation

        def prepare_point(self):
            if self.point and self._ban_point:
                distance = self.point.distance(self._ban_point)

                # We consider that if point address and point are too far, it comes from an incoherent query point, then we remove it
                if distance > 1000:
                    self.point = None

        def prepare_address(self):
            if self.address:
                fetcher = self.__banFetcherCls()
                geocode_results = fetcher.geocode(self.address)

                # If there is any result coming from the geocoder
                if geocode_results["features"]:
                    best = geocode_results["features"][0]

                    # And if the result is good enough
                    if (
                        best["properties"]["score"] > 0.7
                        and best["properties"]["type"] == "housenumber"
                    ):
                        # We set the address point
                        self._ban_point = Point(
                            best["geometry"]["coordinates"], srid=4326
                        ).transform(settings.DEFAULT_SRID, clone=True)

                        # We set the ban id
                        self._ban_id = best["properties"]["id"]

        @property
        def errors(self):
            return self.__errors

        def is_valid(self) -> bool:
            return len(self.__errors) == 0

        def set_page_from_url(self, page: str):
            if self.__validate_page_from_url(page):
                self.set_page(int(page))

        def set_page(self, page: int):
            self.page = page

        def set_sort_from_url(self, sort_str: str) -> None:
            if sort_str is not None:
                self.set_sort(sort_str)

        def set_sort(self, sort: str) -> None:
            if self.__validate_sort(sort):
                self.sort = sort

        def set_point(self, point: Point):
            if self.__validate_point(point):
                self.point = point

        def __validate_sort(self, sort: str) -> bool:
            if sort not in self.SORT_CHOICES:
                self.__errors.append(
                    f"sort : sort parameter must be one of {self.SORT_CHOICES}"
                )
                return False

            return True

        def __validate_page_from_url(self, page: str) -> bool:
            if not page:
                return False

            if not page.isdigit():
                self.__errors.append("page : page parameter must be an integer")
                return False

            return True

        def set_bb_from_url(self, bb_str: str) -> None:
            if bb_str is not None:
                if self.__validate_bb_from_url(bb_str):
                    bb = self.__convert_bb_from_url(bb_str)
                    self.set_bb(bb)

        def set_bb(self, bb) -> None:
            if self.__validate_bb(bb):
                self.bb = bb

        def __convert_bb_from_url(self, bb_str: str) -> Polygon:
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

        def __validate_bb_from_url(self, bb_str: str) -> bool:
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

        def set_address_from_url(self, address_str: str):
            self.set_address(address_str)

        def set_point_from_url(self, point_str: str) -> None:
            if self.__validate_point_from_url(point_str):
                point = self.__convert_point_from_url(point_str)
                self.set_point(point)

        def set_status_from_url(self, status_str: str) -> None:
            if status_str is not None:
                status = self.__convert_status_from_url(status_str)
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

        def __convert_status_from_url(self, status_str: str) -> list:
            if status_str == "all":
                return self.allowed_status
            return status_str.split(",")

        def __validate_point_from_url(self, coords_str: str) -> bool:
            if not coords_str:
                return False

            coords = coords_str.split(",")

            if len(coords) != 2:
                self.__errors.append(
                    f"point: point must have latitude and longitude separated by a comma"
                )
                return False

            if not is_float(coords[0]):
                self.__errors.append("point: latitude is invalid")
                return False

            if not is_float(coords[1]):
                self.__errors.append("point: longitude is invalid")
                return False

            return True

        def __convert_point_from_url(self, coords_str) -> Point:
            lat, lng = coords_str.split(",")

            return Point(float(lng), float(lat), srid=4326)

        def set_point(self, point: Point) -> None:
            if point is not None:
                if self.__validate_point(point):
                    self.point = point

        def __validate_point(self, point: Point) -> bool:
            if point is None:
                return False

            if point.srid is None:
                self.__errors.append("point : point must have a SRID")
                return False

            if not point.valid:
                self.__errors.append(
                    f"point : point is not valid. Reason: {point.valid_reason}"
                )
                return False

            return True

        def set_address(self, address: str):
            if address is not None:
                self.address = address

        def set_poly(self, poly: Polygon) -> None:
            if poly is not None:
                if self.__validate_poly(poly):
                    self.poly = self.__convert_poly(poly)

        def __convert_poly(self, poly: Polygon) -> Polygon:
            if poly.srid == settings.DEFAULT_SRID:
                return poly

            return poly.transform(settings.DEFAULT_SRID, clone=True)

        def __validate_point(self, point: Point) -> bool:
            if not isinstance(point, Point):
                self.__errors.append("point : point must be a Point object")
                return False

            if point.srid is None:
                self.__errors.append("point : point must have a SRID")
                return False

            if not point.valid:
                self.__errors.append(
                    f"point : point is not valid. Reason: {point.valid_reason}"
                )
                return False

            return True

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

        def set_insee_code_from_url(self, code: str) -> None:
            self.set_insee_code(code)

        def set_insee_code(self, code: str) -> None:
            if code is None:
                self.insee_code = None
                self._city_poly = None
            else:
                if self.__validate_insee_code(code):
                    self.insee_code = code
                    self._city_poly = self.__get_city_polygon()

        def __validate_insee_code(self, code):
            if not code:
                return False

            if len(code) != 5:
                self.__errors.append(
                    "insee_code : insee code must be a string of 5 digits"
                )
                return False

            return True

        def __get_city_polygon(self) -> MultiPolygon:
            try:
                city = City.objects.get(code_insee=self.insee_code)
                return city.shape
            except City.DoesNotExist:
                self.__errors.append(
                    f"insee_code : insee code {self.insee_code} does not exist"
                )
                return None

        def set_rnb_id_from_url(self, rnb_id):
            self.set_rnb_id(rnb_id)

        def set_rnb_id(self, rnb_id):
            self.rnb_id = clean_rnb_id(rnb_id)

        def set_name(self, name: str):
            self.name = name
