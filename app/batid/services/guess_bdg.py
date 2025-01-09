from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.db.models import QuerySet
from geopy import distance

from batid.models import Building
from batid.models import Plot
from batid.services.bdg_status import BuildingStatus as BuildingStatusRef
from batid.services.geocoders import BanGeocoder
from batid.services.geocoders import PhotonGeocoder
from batid.utils.misc import is_float


class BuildingGuess:
    MAX_HAUSDORFF_DISTANCE = 4  # This value must be precised with a test set

    def __init__(self):
        self.params = self.BuildingGuessParams()
        self.qs = None
        self.scores = {}

    def set_params(self, **kwargs):
        self.params.set_filters(**kwargs)

    def set_params_from_url(self, **kwargs):
        self.params.set_filters_from_url(**kwargs)

    def get_queryset(self) -> QuerySet:
        # We verify we have at least one required parameter
        self.params.verify_params()
        if not self.params.is_valid():
            return None

        # Before launching the query, we have to transform/convert some parameters (eg: address->geocode->point)
        self.prepare_params()

        # ###################
        # Filters
        # ###################

        selects = ["b.id", "b.rnb_id", "b.status", "b.ext_ids"]
        wheres = ["is_active = TRUE"]
        joins = []
        group_by = None
        params = {}
        self.scores = {}

        # Status
        if self.params.status:
            wheres.append("status IN %(status)s")
            params["status"] = tuple(self.params.status)

        # #########################################
        # OSM Address point
        if self.params._osm_point:
            # Those scores and filters are almost similar to the ones used on the point params

            # ON THIS SIDE OF THE ROAD SCORE
            # We give more score (2 points) when point comes from OSM than from query
            # todo : if we have both point and address, we should use the same cluster for both
            cluster_q = f"SELECT c.cluster FROM (SELECT ST_UnaryUnion(unnest(ST_ClusterIntersecting(shape))) as cluster FROM {Plot._meta.db_table} WHERE ST_DWithin(shape::geography, %(osm_point)s::geography, 300)) c ORDER BY ST_DistanceSphere(c.cluster, %(osm_point)s) ASC LIMIT 1"
            self.scores[
                "osm_point_plot_cluster"
            ] = f"CASE WHEN ST_Intersects(shape, ({cluster_q})) THEN 2 ELSE 0 END"

            # DISTANCE TO THE POINT SCORE
            # We want to keep buildings that are close to the point
            self.scores[
                "osm_point_distance"
            ] = f"CASE WHEN ST_DistanceSphere(shape, %(osm_point)s) >= 1 THEN 2 / ST_DistanceSphere(shape, %(osm_point)s) WHEN ST_DistanceSphere(shape, %(osm_point)s) > 0 THEN 2 ELSE 3 END"

            # Add the point to the params
            params["osm_point"] = f"{self.params._osm_point}"

        # #########################################
        # BAN ID
        if self.params._ban_id:
            joins.append(
                f"LEFT JOIN {Building.addresses_read_only.through._meta.db_table} as b_rel_a ON b_rel_a.building_id = b.id"
            )

            group_by = "b.id"

            self.scores[
                "ban_id_shared"
            ] = f"CASE WHEN %(ban_id)s = ANY(array_agg(b_rel_a.address_id)) THEN 1 ELSE 0 END"
            params["ban_id"] = self.params._ban_id

        # #########################################
        # Ban Address point
        if self.params._ban_point:
            # Those scores and filters are almost similar to the ones used on the point params

            # ON THIS SIDE OF THE ROAD SCORE
            # We give more score (2 points) when point comes from BAN than from query
            # todo : if we have both point and address, we should use the same cluster for both
            cluster_q = f"SELECT c.cluster FROM (SELECT ST_UnaryUnion(unnest(ST_ClusterIntersecting(shape))) as cluster FROM {Plot._meta.db_table} WHERE ST_DWithin(shape::geography, %(ban_point)s::geography, 300)) c ORDER BY ST_DistanceSphere(c.cluster, %(ban_point)s) ASC LIMIT 1"
            self.scores[
                "ban_point_plot_cluster"
            ] = f"CASE WHEN ST_Intersects(shape, ({cluster_q})) THEN 2 ELSE 0 END"

            # DISTANCE TO THE POINT SCORE
            # We want to keep buildings that are close to the point
            # todo : does the double ST_Distance evaluation is a performance problem ?
            self.scores[
                "ban_point_distance"
            ] = f"CASE WHEN ST_DistanceSphere(shape, %(ban_point)s) >= 1 THEN 2 / ST_DistanceSphere(shape, %(ban_point)s) WHEN ST_DistanceSphere(shape, %(ban_point)s) > 0 THEN 2 ELSE 3 END"

            # Add the point to the params
            params["ban_point"] = f"{self.params._ban_point}"

        # #########################################
        # Point

        if self.params.point:
            # ON THIS SIDE OF THE ROAD SCORE
            # Points tend to be on the right side of the road. We can filter out buildings that are on the other side of the road.
            # Public roads are not in cadastre plots. By grouping contiguous plots we can recreate simili-roads and keep only buildings intersecting this plot group.
            # todo : it might be interesting to pre-calculate cluster and store them in DB. It would be faster.
            cluster_q = f"SELECT c.cluster FROM (SELECT ST_UnaryUnion(unnest(ST_ClusterIntersecting(shape))) as cluster FROM {Plot._meta.db_table} WHERE ST_DWithin(shape::geography, %(point)s::geography, 300)) c ORDER BY ST_DistanceSphere(c.cluster, %(point)s) ASC LIMIT 1"
            self.scores[
                "point_plot_cluster"
            ] = f"CASE WHEN ST_Intersects(shape, ({cluster_q})) THEN 1 ELSE 0 END"

            # DISTANCE TO THE POINT SCORE
            # We want to keep buildings that are close to the point
            # todo : does the double ST_Distance evaluation is a performance problem ?
            self.scores[
                "point_distance"
            ] = f"CASE WHEN ST_DistanceSphere(shape, %(point)s) >= 1 THEN 1 / ST_DistanceSphere(shape, %(point)s) WHEN ST_DistanceSphere(shape, %(point)s) > 0 THEN 1 ELSE 5 END"

            # LIMIT THE DISTANCE TO THE POINT
            wheres.append(f"ST_DWithin(shape::geography, %(point)s::geography, 400)")

            # Add the point to the params
            params["point"] = f"{self.params.point}"

        # #########################################
        # Restrict research in a radius around point and address point

        ban_point_where = "ST_DWithin(shape::geography, %(ban_point)s::geography, 400)"
        point_where = "ST_DWithin(shape::geography, %(point)s::geography, 400)"

        if self.params.point and self.params._ban_point:
            wheres.append(f"({ban_point_where} or {point_where})")
        elif self.params.point:
            wheres.append(point_where)
        elif self.params._ban_point:
            wheres.append(ban_point_where)

        # Polygon
        if self.params.poly:
            # warning : ST_HausdorffDistance is in degree when using wgs_84.
            # we need to find a way to fix a meaningful threshold
            # for the time being I use https://epsg.io/4087 because it is a projected CRS (its unit is meters)
            # and it is valid worldwide, but I am absolutely not sure this is precise!
            wheres = [
                "ST_HausdorffDistance(ST_Transform(shape, 4087), st_transform(%(poly)s, 4087)) <= %(max_hausdorff_dist)s"
            ]
            params["poly"] = f"{self.params.poly}"
            params["max_hausdorff_dist"] = self.MAX_HAUSDORFF_DISTANCE

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
        subscores_obj = " "
        if len(self.scores):
            # Total score
            subscore_sum_str = " + ".join(self.scores.keys())
            scores_sum = f", {subscore_sum_str} as score "

            # Subscores
            subscores_struct = ", ".join([f"'{k}', {k}" for k in self.scores.keys()])
            subscores_obj = f", json_build_object({subscores_struct}) as sub_scores "

        # ######################
        # Assembling the queries

        score_query = (
            f"SELECT {select_str} {score_cases_str} "
            f"FROM {Building._meta.db_table} as b {joins_str} "
            f"{where_str} {group_by_str} {order_str}"
        )

        global_query = (
            f"WITH scored_bdgs AS ({score_query}) "
            f"SELECT *  {scores_sum} {subscores_obj} "
            f"FROM scored_bdgs "
            "ORDER BY score DESC "
            f"{pagination_str}"
        )

        qs = Building.objects.raw(global_query, params).prefetch_related(
            "addresses_read_only"
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
        self.params.set_ban_handler_cls = cls

    class BuildingGuessParams:
        SORT_DEFAULT = "rnb_id"
        SORT_CHOICES = ["rnb_id"]

        PARAM_SPLITTER = ","

        def __init__(self, **kwargs):
            # ##########
            # Init properties
            # ##########

            # Filters
            self.status = []

            self.point = None  # Can be any SRID
            self.name = None
            self.address = None
            self.poly = None

            self.sort = None

            # Filters constructed from other filters
            # They can not be set directly
            self._osm_point = None
            self._ban_point = None
            self._ban_id = None

            # Pagination
            self.page = 1

            # Allowed status
            self.allowed_status = BuildingStatusRef.PUBLIC_TYPES_KEYS

            # Internals
            self.__errors = []
            self.__ban_handler_cls = BANGeocodingHandler
            self.__osm_handler_cls = PhotonGeocodingHandler

        def set_filters(self, **kwargs):
            if "name" in kwargs:
                self.set_name(kwargs["name"])

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

            if "page" in kwargs:
                self.set_page(kwargs["page"])

        def set_filters_from_url(self, **kwargs):
            # ##########
            # Set up filters
            # ##########

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

            if "page" in kwargs:
                self.set_page_from_url(kwargs["page"])

        def set_ban_handler_cls(self, cls):
            self.__ban_handler_cls = cls

        def set_osm_handler_cls(self, cls):
            self.__osm_handler_cls = cls

        def prepare_params(self):
            self.prepare_address()
            self.prepare_point()  # Point preparation must be done after address preparation

        def prepare_point(self):
            if self.point and self._ban_point:
                distance = compute_distance(self.point, self._ban_point)

                # We consider that if point address and point are too far, it comes from an incoherent query point, then we remove it
                if distance > 1000:
                    self.point = None

        def prepare_address(self):
            # We have to geocode from BAN first. The BAN point will be used by the OSM geocoder.
            if self.address:
                self.geocode_from_ban()

            if self.name or self.address:
                self.geocode_from_osm()

        def geocode_from_osm(self):
            handler = self.__osm_handler_cls()
            self._osm_point = handler.geocode(self)

        def geocode_from_ban(self):
            handler = self.__ban_handler_cls()
            handler.geocode(self)

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

            if float(coords[0]) < -90 or float(coords[0]) > 90:
                self.__errors.append("point: latitude must be between -90 and 90")
                return False

            if float(coords[1]) < -180 or float(coords[1]) > 180:
                self.__errors.append("point: longitude must be between -180 and 180")
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
                    self.poly = poly

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

        def set_name(self, name: str):
            self.name = name

        def verify_params(self):
            if not self.address and not self.name and not self.point and not self.poly:
                self.__errors.append(
                    "You must provide at least one of the following parameters: address, name, point, poly"
                )


class PhotonGeocodingHandler:
    def __init__(self):
        self.geocoder = PhotonGeocoder()

    def geocode_params(self, search_params):
        params = {"q": search_params.name, "lang": "fr", "limit": 1}

        if isinstance(search_params._ban_point, Point):
            ban_point = search_params._ban_point.transform(4326, clone=True)

            params["lon"] = ban_point.x
            params["lat"] = ban_point.y

        elif isinstance(search_params.address, str):
            q_elements = []
            if isinstance(search_params.name, str):
                q_elements.append(search_params.name)
            if isinstance(search_params.address, str):
                q_elements.append(search_params.address)

            params["q"] = " ".join(q_elements)

        return params

    def geocode(self, search_params):
        if search_params.address is None and search_params.name is None:
            raise Exception(
                "Missing 'address' or 'name' parameter for Photon geocoding"
            )

        params = self.geocode_params(search_params)

        if isinstance(params["q"], str):
            geocode_response = self.geocoder.geocode(params)
            results = geocode_response.json()

            if results["features"]:
                best = results["features"][0]

                search_params._osm_point = Point(
                    best["geometry"]["coordinates"], srid=4326
                )


class BANGeocodingHandler:
    def __init__(self):
        self.geocoder = BanGeocoder()

    def geocode(self, search_params):
        address = search_params.address

        geocode_response = self.geocoder.geocode({"q": address})
        results = geocode_response.json()

        # If there is any result coming from the geocoder
        if "features" in results and results["features"]:
            best = results["features"][0]

            # And if the result is good enough
            if (
                best["properties"]["score"] >= 0.7
                and best["properties"]["type"] == "housenumber"
            ):
                # We set the address point
                search_params._ban_point = Point(
                    best["geometry"]["coordinates"], srid=4326
                )

                # We set the ban id
                search_params._ban_id = best["properties"]["id"]


def compute_distance(a, b):
    # we use geopy package to compute distance using the WGS84 ellipsoid
    if a.srid != 4326:
        a = a.transform(4326, clone=True)
    if b.srid != 4326:
        b = b.transform(4326, clone=True)
    return distance.distance((a.y, a.x), (b.y, b.x)).meters
