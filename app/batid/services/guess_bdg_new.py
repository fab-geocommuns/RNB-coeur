import concurrent
import json
import time
from abc import ABC
from abc import abstractmethod
from typing import Optional

import pandas as pd
from django.contrib.gis.geos import Point
from django.db import connections

from batid.models import Building
from batid.services.closest_bdg import get_closest
from batid.services.geocoders import BanGeocoder
from batid.services.geocoders import PhotonGeocoder


class Guesser:
    STEP_CLOSEST_FROM_POINT = "closest_from_point"
    STEP_GEOCODE_ADDRESS = "geocode_address"
    STEP_GEOCODE_NAME = "geocode_name"

    def __init__(self):
        self.guesses = {}
        self.handlers = [
            ClosestFromPointHandler(),
            GeocodeAddressHandler(),
            GeocodeNameHandler(),
        ]

    def create_work_file(self, inputs, file_path):
        self.load_inputs(inputs)
        self.save_work_file(file_path)

    def load_work_file(self, file_path):
        with open(file_path, "r") as f:
            self.guesses = json.load(f)

    def load_inputs(self, inputs: list):
        self._validate_inputs(inputs)
        self.guesses = self._inputs_to_guesses(inputs)

    def guess_work_file(self, file_path):
        self.load_work_file(file_path)

        batches = self._guesses_to_batches()

        for batch in batches:
            batch = self.guess_batch(batch)
            self.guesses.update(batch)
            self.save_work_file(file_path)

    def guess_all(self):
        batches = self._guesses_to_batches()

        for batch in batches:
            batch = self.guess_batch(batch)
            self.guesses.update(batch)

    def _guesses_to_batches(self, batch_size: int = 300):
        batches = []
        batch = {}

        c = 0
        for ext_id, guess in self.guesses.items():
            c += 1
            batch[ext_id] = guess

            if len(batch) == batch_size or ext_id == list(self.guesses.keys())[-1]:
                batches.append(batch)
                batch = {}

        return batches

    def report(self):
        data = list(self.guesses.values())

        print("-- Report --")

        df = pd.json_normalize(data, sep="_")

        # Count number of rows
        total = len(df)
        print(f"Number of rows: {total}")

        # Number and percetange of rows where match_rnb_id is not null
        match_count = df["match_rnb_id"].notnull().sum()
        match_percentage = match_count / total * 100
        print(f"Number of match: {match_count} ({match_percentage:.2f}%)")

        # Display table of all march_reason values with their absolute count and their percentage

        match_reason_count = df["match_reason"].value_counts()
        match_reason_percentage = match_reason_count / total * 100
        print("\n-- match_reasons : absolute --")
        print(match_reason_count)
        print("\n-- match_reasons : % --")
        print(match_reason_percentage)

    def save_work_file(self, file_path):
        self.convert_matches()

        with open(file_path, "w") as f:
            json.dump(self.guesses, f, indent=4)

    def convert_matches(self):
        for ext_id, guess in self.guesses.items():
            if guess["match"] and isinstance(guess["match"], Building):
                guess["match"] = {
                    "rnb_id": guess["match"].rnb_id,
                    "lat_lng": f"{guess['match'].point[1]}, {guess['match'].point[0]}",
                    "distance": guess["match"].distance.m,
                }

    def guess_batch(self, guesses: dict) -> dict:
        for handler in self.handlers:
            if not isinstance(handler, AbstractHandler):
                raise ValueError("Handler must be an instance of AbstractHandler")

            guesses = handler.handle(guesses)

        return guesses

    @staticmethod
    def _inputs_to_guesses(inputs) -> dict:
        guesses = {}
        for input in inputs:
            ext_id = input["ext_id"]
            guesses[ext_id] = {
                "input": input,
                "match": None,
                "match_reason": None,
                "finished_steps": [],
            }

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

    @staticmethod
    def _validate_ext_ids(inputs):
        ext_ids = [d["ext_id"] for d in inputs]
        if len(ext_ids) != len(set(ext_ids)):
            raise Exception("ext_ids are not unique")


class AbstractHandler(ABC):
    _name = None

    def handle(self, guesses: dict) -> dict:
        to_guess, to_not_guess = self._split_guesses(guesses)
        to_guess = self._guess_batch(guesses)

        guesses = to_guess | to_not_guess
        guesses = self._add_finished_step(guesses)

        return guesses

    def _split_guesses(self, guesses: dict) -> tuple:
        to_handle = {}
        not_to_handle = {}

        for ext_id, guess in guesses.items():
            if self.name not in guess["finished_steps"] and guess["match"] is None:
                to_handle[ext_id] = guess
            else:
                not_to_handle[ext_id] = guess

        return to_handle, not_to_handle

    @abstractmethod
    def _guess_batch(self, guesses: dict) -> dict:
        # This function is the one doing all the guess work. It must be implemented in each handler.
        raise NotImplementedError

    @property
    def name(self):
        if self._name is None:
            raise ValueError("_name must be set")
        return self._name

    def _add_finished_step(self, guesses: dict) -> dict:
        for guess in guesses.values():
            if self.name not in guess["finished_steps"]:
                guess["finished_steps"].append(self.name)
        return guesses


class ClosestFromPointHandler(AbstractHandler):
    _name = "closest_from_point"

    def __init__(self, closest_radius=30, isolated_bdg_max_distance=8):
        self.closest_radius = closest_radius
        self.isolated_bdg_max_distance = isolated_bdg_max_distance

    def _guess_batch(self, guesses: dict) -> dict:
        tasks = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for guess in guesses.values():
                future = executor.submit(self._guess_one, guess)
                future.add_done_callback(lambda future: connections.close_all())
                tasks.append(future)

            for future in concurrent.futures.as_completed(tasks):
                guess = future.result()
                guesses[guess["input"]["ext_id"]] = guess

        return guesses

    def _guess_one(self, guess: dict) -> dict:
        lat = guess["input"].get("lat", None)
        lng = guess["input"].get("lng", None)

        if not lat or not lng:
            return guess

        # Get the two closest buildings
        closest_bdgs = get_closest(lat, lng, self.closest_radius)[:2]

        if not closest_bdgs:
            return guess

        first_bdg = closest_bdgs[0]
        # Is the the point is in the first building ?
        if first_bdg.distance.m <= 0:
            guess["match"] = first_bdg
            guess["match_reason"] = "point_on_bdg"
            return guess

        # Is the first building within 8 meters and the second building is far enough ?
        if first_bdg.distance.m <= self.isolated_bdg_max_distance:
            if len(closest_bdgs) == 1:
                # There is only one building close enough. No need to compare to the second one.
                guess["match"] = first_bdg
                guess["match_reason"] = "isolated_closest_bdg"
                return guess

            if len(closest_bdgs) > 1:
                # There is at least one other close building. We compare the two closest buildings distance to the point.
                second_bdg = closest_bdgs[1]
                min_second_bdg_distance = self._min_second_bdg_distance(
                    first_bdg.distance.m
                )
                if second_bdg.distance.m >= min_second_bdg_distance:
                    guess["match"] = first_bdg
                    guess["match_reason"] = "isolated_closest_bdg"
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

    def _guess_batch(self, guesses: dict) -> dict:
        for guess in guesses.values():
            guess = self._guess_one(guess)
            guesses[guess["input"]["ext_id"]] = guess

        return guesses

    def _guess_one(self, guess: dict) -> dict:
        lat = guess["input"].get("lat", None)
        lng = guess["input"].get("lng", None)
        address = guess["input"].get("address", None)

        if not address or not lat or not lng:
            return guess

        # We sleep a little bit to avoid being throttled by the geocoder
        time.sleep(self.sleep_time)

        ban_id = self._address_to_ban_id(address, lat, lng)

        if ban_id:
            close_bdg_w_ban_id = get_closest(lat, lng, self.closest_radius).filter(
                addresses__id=ban_id
            )

            if close_bdg_w_ban_id.count() == 1:
                guess["match"] = close_bdg_w_ban_id.first()
                guess["match_reason"] = "precise_address_match"

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

    def _guess_batch(self, guesses: dict) -> dict:
        for guess in guesses.values():
            guess = self._guess_one(guess)
            guesses[guess["input"]["ext_id"]] = guess

        return guesses

    def _guess_one(self, guess: dict) -> dict:
        lat = guess["input"].get("lat", None)
        lng = guess["input"].get("lng", None)
        name = guess["input"].get("name", None)

        if not lat or not lng or not name:
            return guess

        # We sleep a little bit to avoid being throttled by the geocoder
        time.sleep(self.sleep_time)

        osm_bdg_point = self._geocode_name_and_point(name, lat, lng)

        if osm_bdg_point:
            # todo : on devrait filtrer pour n'avoir que les bâtiments qui ont un statut de bâtiment réel
            bdg = Building.objects.filter(shape__contains=osm_bdg_point).first()

            if isinstance(bdg, Building):
                guess["match"] = bdg
                guess["match_reason"] = "found_name_in_osm"
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
