import json
from pprint import pprint
from typing import Optional

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point

from batid.models import Building
from batid.services.geocoders import PhotonGeocoder
from geopy import distance


class BuildingGuess:

    """
    On créé un nouveau système de guess plus simple que le guess précédent
    Fonctionnement :
    - On regarde les paramètres dans l'ordre suivant :
        - le point
        - le nom
        - l'adresse

    """

    MIN_CONFIDENCE_SCORE = 10

    def __init__(self):
        self.params = self.BuildingGuessParams()

        self.bdgs = {}

    def __set_params(self, **kwargs):
        self.params.set_filters(**kwargs)

    def guess(self, params):
        self.__set_params(**params)

        # ##################################
        # First we can check with point only
        if self.params.point:
            self.__handle_point()

            # We are confident enough, we can stop here
            if self.confident_guess:
                return self.results

        # ##################################
        # Then we can check with name and point
        if self.params.name and self.params.point:
            self.__handle_name_and_point()

            # We are confident enough, we can stop here
            if self.confident_guess:
                return self.results

    def __handle_name_and_point(self):
        osm_bdg_point = _geocode_name_and_point(self.params.name, self.params.point)

        if osm_bdg_point:
            # We already fetched bdgs around the point params, we don't need to fetch them again
            self.__rate_results_w_osm_point(osm_bdg_point)

    def __rate_results_w_osm_point(self, osm_bdg_point: Point):
        for rnb_id, bdg in self.bdgs.items():
            if bdg.shape.contains(osm_bdg_point):
                self.bdgs[rnb_id].subscores["osm_point_on_bdg"] = 10

    @property
    def results(self):
        results = [bdg for bdg in list(self.bdgs.values()) if bdg.score > 0]
        return results[:5]

    @property
    def confident_guess(self):
        self._calc_scores()
        self._sort_bdgs()
        return self._eval_confidence()

    def __handle_point(self):
        self.__fetch_bdgs_around_point()
        self.__rate_results_w_point()

    def __add_bdgs(self, bdgs):
        for bdg in bdgs:
            rnb_id = bdg.rnb_id

            if rnb_id not in self.bdgs:
                self.bdgs[rnb_id] = bdg
                self.bdgs[rnb_id].subscores = {}

    def __add_rated_bdgs(self, bdgs):
        for bdg in bdgs:
            rnb_id = bdg.rnb_id

            if rnb_id not in self.bdgs:
                self.bdgs[rnb_id] = bdg
            else:
                # Merge subscores
                self.bdgs[rnb_id].subscores = (
                    self.bdgs[rnb_id].subscores | bdg.subscores
                )

    def _calc_scores(self):
        for bdg in self.bdgs.values():
            bdg.score = sum(bdg.subscores.values())

    def _sort_bdgs(self):
        self.bdgs = dict(
            sorted(self.bdgs.items(), key=lambda item: item[1].score, reverse=True)
        )

    def _eval_confidence(self):
        # No results : no confidence
        if len(self.bdgs) == 0:
            return False

        # First result has a score too low : no confidence
        first_score = list(self.bdgs.values())[0].score
        if first_score < self.MIN_CONFIDENCE_SCORE:
            return False

        # First result has the same score as the second one : no confidence
        if len(self.bdgs) > 1:
            second_score = list(self.bdgs.values())[1].score
            if second_score == first_score:
                return False

        return True

    def __fetch_bdgs_around_point(self):
        qs = Building.objects.all()
        qs = (
            qs.extra(
                where=[
                    f"ST_DWITHIN(shape::geography, ST_MakePoint({self.params.point[0]}, {self.params.point[1]})::geography, 100)"
                ]
            )
            .annotate(distance=Distance("shape", self.params.point))
            .order_by("distance")
        )

        self.__add_bdgs(list(qs))

    def __rate_results_w_point(self):
        distances = []

        for rnb_id, bdg in self.bdgs.items():
            # check if we have a distance attribute
            if hasattr(bdg, "distance"):
                distances.append((rnb_id, bdg.distance.m))

        # We sort the distances
        distances = sorted(distances, key=lambda x: x[1])

        # loop on all distance
        for idx, (rnb_id, distance) in enumerate(distances):
            # Far building
            if distance >= 20:
                self.bdgs[rnb_id].subscores["point_distance"] = 0

            # Close building but not that close
            if distance <= 5 and distance > 1:
                self.bdgs[rnb_id].subscores["point_distance"] = 5

            # Point on the building ! This is the one.
            if distance <= 1:
                self.bdgs[rnb_id].subscores["point_distance"] = 15

            # We add extra point to the first building if the second one is far enough
            if idx == 0 and len(self.bdgs) > 1:
                if distance > 1:
                    second_bdg_distance = distances[1][1]
                    min_second_bdg_distance = _min_second_bdg_distance(distance)
                    if second_bdg_distance > min_second_bdg_distance:
                        self.bdgs[rnb_id].subscores["point_second_bdg_far_enough"] = 5

    class BuildingGuessParams:
        def __init__(self):
            self.point = None
            self.name = None
            self.address = None

        def set_filters(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

            return self


def _min_second_bdg_distance(first_bdg_distance: float) -> float:
    # The formula has been built here : https://chat.openai.com/share/116eeabc-9ba0-4b2e-902f-2291277ef879
    ratio = 1.82 ** (-0.202 * first_bdg_distance) + 1.3
    return first_bdg_distance * ratio


def _geocode_name_and_point(name: str, point: Point) -> Optional[Point]:
    geocode_params = {
        "q": name,
        "lat": point[1],
        "lon": point[0],
        "lang": "fr",
        "limit": 1,
    }

    geocoder = PhotonGeocoder()
    geo_result = geocoder.geocode(geocode_params)

    if geo_result["features"] and geo_result["features"][0]["properties"]["type"] in [
        "building",
        "house",
        "construction",
    ]:
        lat = geo_result["features"][0]["geometry"]["coordinates"][1]
        lng = geo_result["features"][0]["geometry"]["coordinates"][0]
        return Point(lng, lat, srid=4326)
    else:
        return
