import concurrent
import json
import time
from abc import ABC
from abc import abstractmethod
from typing import Optional
import pandas as pd
from django.contrib.gis.geos import Point, GEOSGeometry, Polygon
from django.db import connections
from batid.models import Building, Guess
from batid.services.closest_bdg import get_closest_from_point, get_closest_from_poly
from batid.services.geocoders import BanGeocoder
from batid.services.geocoders import PhotonGeocoder


class Guesser:
    def __init__(self):
        self.persister = GuessInMemoryPersister()
        self.handlers = [
            ClosestFromPointHandler(),
            GeocodeAddressHandler(),
            GeocodeNameHandler(),
        ]
        self.batch_size = 500

    @property
    def guesses(self):
        return self.persister.all_guesses()

    def load_inputs(self, inputs: list):
        self._validate_inputs(inputs)

        guesses = self._inputs_to_guesses(inputs)
        self.persister.save(guesses)

    def guess_all(self):
        total = 0

        while True:
            unfinished_guesses = self.persister.get_unfinished_guesses(self.batch_size)

            if not unfinished_guesses:
                break

            finished_guesses = self._guess_batch(unfinished_guesses)
            self.persister.save(finished_guesses)

            total += len(finished_guesses)

            if total % 1000 == 0:
                print(f"Done {total} guesses")

    def report(self):
        raise NotImplementedError(
            "TODO : corriger cette methode pour qu'elle fonctionne avec le nouveau format de guess"
        )

        # data = list(self.guesses.values())
        #
        # print("-- Report --")
        #
        # df = pd.json_normalize(data, sep="_")
        #
        # # Count number of rows
        # total = len(df)
        # print(f"Number of rows: {total}")
        #
        # # Number and percetange of rows where match_rnb_id is not null
        # match_count = df["match_reason"].notnull().sum()
        # match_percentage = match_count / total * 100
        # print(f"Number of match: {match_count} ({match_percentage:.2f}%)")
        #
        # # Display table of all march_reason values with their absolute count and their percentage
        #
        # match_reason_count = df["match_reason"].value_counts()
        # match_reason_percentage = match_reason_count / total * 100
        # print("\n-- match_reasons : absolute --")
        # print(match_reason_count)
        # print("\n-- match_reasons : % --")
        # print(match_reason_percentage)

    def display_reason(
        self,
        reason: str,
        count: int = 10,
        cols: list = ("input_ext_id", "match_rnb_id", "match_reason"),
    ):
        raise NotImplementedError(
            "TODO : corriger cette methode pour qu'elle fonctionne avec le nouveau format de guess"
        )

        # data = list(self.guesses.values())
        #
        # df = pd.json_normalize(data, sep="_")
        #
        # reasons = df[df["match_reason"] == reason]
        # reasons = reasons[cols]
        #
        # print(reasons.sample(count))

    def display_nomatches(self, count: int = 10):
        raise NotImplementedError(
            "TODO : corriger cette methode pour qu'elle fonctionne avec le nouveau format de guess"
        )

        # data = list(self.guesses.values())
        #
        # df = pd.json_normalize(data, sep="_")
        #
        # nomatches = df[df["match_rnb_id"].isnull()]
        # nomatches = nomatches[["input_ext_id"]]
        #
        # print(nomatches.sample(count))

    def save_work_file(self, file_path):
        self.convert_matches()

        with open(file_path, "w") as f:
            json.dump(self.guesses, f, indent=4)

    def convert_matches(self):
        for ext_id, guess in self.guesses.items():
            if guess["matches"] and not isinstance(guess["matches"], str):
                rnb_ids = []

                for idx, match in enumerate(guess["matches"]):
                    rnb_ids.append(match.rnb_id)

                guess["matches"] = ",".join(rnb_ids)

    def _guess_batch(self, guesses: list) -> list:
        for handler in self.handlers:
            if not isinstance(handler, AbstractHandler):
                raise ValueError("Handler must be an instance of AbstractHandler")

            guesses = handler.handle(guesses)

        # Set guess to finished
        for guess in guesses:
            guess.finished = True

        return guesses

    @staticmethod
    def _inputs_to_guesses(inputs) -> list:
        guesses = []
        for input in inputs:
            # Always transform ext_id to string
            ext_id = str(input["ext_id"])
            # We don't need ext_id in the input anymore
            del input["ext_id"]

            guesses.append(
                Guess(
                    matches=[],
                    finished=False,
                    finished_steps=[],
                    inputs=input,
                    ext_id=ext_id,
                )
            )

        return guesses

    @staticmethod
    def _validate_inputs(inputs):
        Guesser._validate_types(inputs)
        Guesser._validate_ext_ids(inputs)

    @staticmethod
    def _validate_types(inputs):
        for input in inputs:
            if not isinstance(input, dict):
                raise Exception("data must be a list of dicts")

            if "ext_id" not in input:
                raise Exception("ext_id is required for each input")

            if "polygon" in input and not isinstance(input["polygon"], dict):
                raise Exception("polygon must be a geojson geometry formatted dict")

    @staticmethod
    def _validate_ext_ids(inputs):
        ext_ids = [d["ext_id"] for d in inputs]
        if len(ext_ids) != len(set(ext_ids)):
            raise Exception("ext_ids are not unique")


class AbstractHandler(ABC):
    _name = None

    def handle(self, guesses: list) -> list:
        to_guess, to_not_guess = self._split_guesses(guesses)
        to_guess = self._guess_batch(guesses)

        guesses = to_guess + to_not_guess
        guesses = self._add_finished_step(guesses)

        return guesses

    def _split_guesses(self, guesses: list) -> tuple:
        to_handle = []
        not_to_handle = []

        for guess in guesses:
            if self.name not in guess.finished_steps and len(guess.matches) == 0:
                to_handle.append(guess)
            else:
                not_to_handle.append(guess)

        return to_handle, not_to_handle

    @abstractmethod
    def _guess_batch(self, guesses: list) -> list:
        # This function is the one doing all the guess work. It must be implemented in each handler.
        raise NotImplementedError

    @property
    def name(self):
        if self._name is None:
            raise ValueError("_name must be set")
        return self._name

    def _add_finished_step(self, guesses: list) -> list:
        for guess in guesses:
            if self.name not in guess.finished_steps:
                guess.finished_steps.append(self.name)
        return guesses


class ClosestFromPointHandler(AbstractHandler):
    _name = "closest_from_point"

    def __init__(self, closest_radius=30, isolated_bdg_max_distance=8):
        self.closest_radius = closest_radius
        self.isolated_bdg_max_distance = isolated_bdg_max_distance

    def _guess_batch(self, guesses: list) -> list:
        tasks = []
        result = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for guess in guesses:
                future = executor.submit(self._guess_one, guess)
                future.add_done_callback(lambda future: connections.close_all())
                tasks.append(future)

            for future in concurrent.futures.as_completed(tasks):
                result.append(future.result())

        return result

    def _guess_one(self, guess: Guess) -> Guess:
        lat = guess.inputs.get("lat", None)
        lng = guess.inputs.get("lng", None)

        if not lat or not lng:
            return guess

        # Get the two closest buildings
        closest_bdgs = get_closest_from_point(lat, lng, self.closest_radius)[:2]

        if not closest_bdgs:
            return guess

        first_bdg = closest_bdgs[0]
        # Is the the point is in the first building ?
        if first_bdg.distance.m <= 0:
            guess.matches.append(first_bdg.rnb_id)
            guess.match_reason = "point_on_bdg"
            return guess

        # Is the first building within 8 meters and the second building is far enough ?
        if first_bdg.distance.m <= self.isolated_bdg_max_distance:
            if len(closest_bdgs) == 1:
                # There is only one building close enough. No need to compare to the second one.
                guess.matches.append(first_bdg.rnb_id)
                guess.match_reason = "isolated_closest_bdg"
                return guess

            if len(closest_bdgs) > 1:
                # There is at least one other close building. We compare the two closest buildings distance to the point.
                second_bdg = closest_bdgs[1]
                min_second_bdg_distance = self._min_second_bdg_distance(
                    first_bdg.distance.m
                )
                if second_bdg.distance.m >= min_second_bdg_distance:
                    guess.matches.append(first_bdg.rnb_id)
                    guess.match_reason = "isolated_closest_bdg"
                    return guess

        # We did not find anything. We return guess as it was sent.
        return guess

    @staticmethod
    def _min_second_bdg_distance(first_bdg_distance: float) -> float:
        # The second building must be at least 10 meters away from the point
        min_distance_floor = 10.0

        # The second building must be at least 3 times the distance of the first building
        ratio = 3
        min_distance_w_ratio = first_bdg_distance * ratio

        return max(min_distance_floor, min_distance_w_ratio)


class GeocodeAddressHandler(AbstractHandler):
    _name = "geocode_address"

    def __init__(self, sleep_time=0.8, closest_radius=100):
        self.sleep_time = sleep_time
        self.closest_radius = closest_radius

    def _guess_batch(self, guesses: list) -> list:
        return [self._guess_one(guess) for guess in guesses]

    def _guess_one(self, guess: Guess) -> Guess:
        lat = guess.inputs.get("lat", None)
        lng = guess.inputs.get("lng", None)
        address = guess.inputs.get("address", None)

        if not address or not lat or not lng:
            return guess

        # We sleep a little bit to avoid being throttled by the geocoder
        time.sleep(self.sleep_time)

        ban_id = self._address_to_ban_id(address, lat, lng)

        if ban_id:
            close_bdg_w_ban_id = get_closest_from_point(
                lat, lng, self.closest_radius
            ).filter(addresses__id=ban_id)

            if close_bdg_w_ban_id.count() == 1:
                guess.matches.append(close_bdg_w_ban_id.first().rnb_id)
                guess.match_reason = "precise_address_match"

        return guess

    @staticmethod
    def _address_to_ban_id(address: str, lat: float, lng: float) -> Optional[str]:
        geocoder = BanGeocoder()
        geocode_response = geocoder.geocode(
            {
                "q": address,
                "lat": lat,
                "lon": lng,
                "type": "housenumber",
            }
        )

        if geocode_response.status_code != 200:
            return

        geo_results = geocode_response.json()

        if "features" in geo_results and geo_results["features"]:
            best = geo_results["features"][0]

            if best["properties"]["score"] >= 0.8:
                return best["properties"]["id"]


class GeocodeNameHandler(AbstractHandler):
    _name = "geocode_name"

    def __init__(self, sleep_time=0.8):
        self.sleep_time = sleep_time

    def _guess_batch(self, guesses: list) -> list:
        return [self._guess_one(guess) for guess in guesses]

    def _guess_one(self, guess: Guess) -> Guess:
        lat = guess.inputs.get("lat", None)
        lng = guess.inputs.get("lng", None)
        name = guess.inputs.get("name", None)

        if not lat or not lng or not name:
            return guess

        # We sleep a little bit to avoid being throttled by the geocoder
        time.sleep(self.sleep_time)

        osm_bdg_point = self._geocode_name_and_point(name, lat, lng)

        if osm_bdg_point:
            # todo : on devrait filtrer pour n'avoir que les bâtiments qui ont un statut de bâtiment réel
            bdg = Building.objects.filter(shape__contains=osm_bdg_point).first()

            if isinstance(bdg, Building):
                guess.matches.append(bdg.rnb_id)
                guess.match_reason = "found_name_in_osm"
                return guess

        return guess

    @staticmethod
    def _geocode_name_and_point(name: str, lat: float, lng: float) -> Optional[Point]:
        geocode_params = {
            "q": name,
            "lat": lat,
            "lon": lng,
            "lang": "fr",
            "limit": 1,
        }

        geocoder = PhotonGeocoder()

        response = geocoder.geocode(geocode_params)

        geo_result = response.json()

        if geo_result.get("features", None) and geo_result["features"][0]["properties"][
            "type"
        ] in [
            "building",
            "house",
            "construction",
        ]:
            lat = geo_result["features"][0]["geometry"]["coordinates"][1]
            lng = geo_result["features"][0]["geometry"]["coordinates"][0]
            return Point(lng, lat, srid=4326)
        else:
            return


class PartialRoofHandler(AbstractHandler):
    """
    This handler is used to match a building based on a roof section.
    """

    _name = "partial_roof"

    def __init__(self, isolated_section_max_distance=1, min_second_bdg_distance=6):
        self.isolated_section_max_distance = isolated_section_max_distance
        self.min_second_bdg_distance = min_second_bdg_distance

    def _guess_batch(self, guesses: list) -> list:
        tasks = []
        result = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for guess in guesses:
                future = executor.submit(self._guess_one, guess)
                future.add_done_callback(lambda future: connections.close_all())
                tasks.append(future)

            for future in concurrent.futures.as_completed(tasks):
                result.append(future.result())

        return result

    def _guess_one(self, guess: Guess) -> Guess:
        roof_geojson = guess.inputs.get("polygon", None)

        if not roof_geojson:
            return guess

        roof_poly = GEOSGeometry(json.dumps(roof_geojson))

        # Get the two closest buildings
        closest_bdgs = get_closest_from_poly(roof_poly, 35)[:20]

        if not closest_bdgs:
            return guess

        # Est-ce qu'il y a un seul batiment qui couvre à plus de X% le pan de toit ?
        sole_bdg_intersecting_enough = self._roof_interesected_enough_by_one_bdg(
            roof_poly, closest_bdgs
        )
        if isinstance(sole_bdg_intersecting_enough, Building):
            guess.matches.append(sole_bdg_intersecting_enough.rnb_id)
            guess.match_reason = "sole_bdg_intersects_roof_enough"
            return guess

        # Est-ce qu'il yn seul bâtiment qui intersects et le second bâtiment le plus proche est assez loin ?
        if self._isolated_bdg_intersecting(roof_poly, closest_bdgs):
            guess.matches.append(closest_bdgs[0].rnb_id)
            guess.match_reason = "isolated_bdg_intersects_roof"
            return guess

        bdgs_covered_enough = self._many_bdgs_covered_enough(roof_poly, closest_bdgs)
        if bdgs_covered_enough:
            rnb_ids = [bdg.rnb_id for bdg in bdgs_covered_enough]
            guess.matches = rnb_ids
            guess.match_reason = "many_bdgs_covered_enough_by_roof"
            return guess

        # No match :(
        return guess

    def _many_bdgs_covered_enough(self, roof_poly: Polygon, closest_bdgs: list) -> list:
        matches = []

        for bdg in closest_bdgs:
            bdg_area = bdg.shape.area
            if bdg_area <= 0:
                continue

            intersection_percentage = bdg.shape.intersection(roof_poly).area / bdg_area

            if intersection_percentage >= 0.80:
                bdg.match_details = {"intersection_percentage": intersection_percentage}
                matches.append(bdg)

        return matches

    def _closest_bdg_contains_roof(
        self, roof_poly: GEOSGeometry, closest_bdgs: list
    ) -> bool:
        first_bdg = closest_bdgs[0]
        return first_bdg.shape.contains(roof_poly)

    def _roof_interesected_enough_by_one_bdg(
        self, roof_poly: GEOSGeometry, closest_bdgs: list
    ) -> bool:
        matches = []

        for bdg in closest_bdgs:
            intersection_percentage = (
                bdg.shape.intersection(roof_poly).area / roof_poly.area
            )

            if intersection_percentage >= 0.25:
                bdg.match_details = {"intersection_percentage": intersection_percentage}
                matches.append(bdg)

        if len(matches) == 1:
            return matches[0]

    def _isolated_bdg_intersecting(
        self, roof_poly: GEOSGeometry, closest_bdgs: list
    ) -> bool:
        # If first building does not intersect the roof, we return False
        if not roof_poly.intersects(closest_bdgs[0].shape):
            return False

        if len(closest_bdgs) == 1:
            return True

        second_bdg = closest_bdgs[1]

        return second_bdg.distance.m >= self.min_second_bdg_distance


class AbstractPersister(ABC):
    @abstractmethod
    def save(self, guesses: list):
        pass

    @abstractmethod
    def get_unfinished_guesses(self, limit: int) -> list:
        pass

    @abstractmethod
    def all_guesses(self) -> list:
        pass


class GuessInMemoryPersister(AbstractPersister):
    def __init__(self):
        self._guesses = {}

    def all_guesses(self) -> list:
        return list(self._guesses.values())

    def save(self, guesses: list):
        for guess in guesses:
            self._guesses[guess.ext_id] = guess

    def get_unfinished_guesses(self, limit: int) -> list:
        unfinished_guesses = [
            guess for guess in self._guesses.values() if not guess.finished
        ]
        return unfinished_guesses[:limit]


class GuessSqlitePersister(AbstractPersister):
    def __init__(self, source_name):
        self.source_name = source_name

    def all_guesses(self) -> list:
        qs = Guess.objects.filter(source_name=self.source_name)
        return list(qs)

    def get_unfinished_guesses(self, limit: int) -> list:
        qs = Guess.objects.filter(
            source_name=self.source_name, finished=False
        ).order_by("id")[:limit]

        return list(qs)

    def save(self, guesses):
        done = 0
        total = len(guesses)

        for guess in guesses:
            Guess.objects.update_or_create(
                ext_id=guess.ext_id,
                source_name=self.source_name,
                defaults={
                    "ext_id": guess.ext_id,
                    "source_name": self.source_name,
                    "inputs": guess.inputs,
                    "matches": guess.matches,
                    "match_reason": guess.match_reason,
                    "finished_steps": guess.finished_steps,
                },
            )

            done += 1

            if done % 1000 == 0:
                print(f"Done {done}/{total}")
