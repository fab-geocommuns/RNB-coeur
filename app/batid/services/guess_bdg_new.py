import concurrent
import json
import time
from pprint import pprint
from typing import Optional
from django.contrib.gis.geos import Point
import pandas as pd
from django.db import connections

from batid.models import Building
from batid.services.closest_bdg import get_closest
from batid.services.geocoders import PhotonGeocoder, BanGeocoder


class Guesser:
    STEP_CLOSEST_FROM_POINT = "closest_from_point"
    STEP_GEOCODE_ADDRESS = "geocode_address"
    STEP_GEOCODE_NAME = "geocode_name"

    def __init__(self):
        self.guesses = {}

    def create_work_file(self, rows, file_path):
        self.load_rows(rows)
        self.save_work_file(file_path)

    def load_work_file(self, file_path):
        with open(file_path, "r") as f:
            self.guesses = json.load(f)

    def load_rows(self, rows: list):
        self._validate_rows(rows)
        self.guesses = self._rows_to_guesses(rows)

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

    @classmethod
    def guess_batch(cls, guesses: dict) -> dict:
        # First try : closest building from point
        guesses = cls._do_many_closest_building(guesses)
        guesses = cls._add_finished_step(cls.STEP_CLOSEST_FROM_POINT, guesses)

        # Second try : geocode address with BAN
        guesses = cls._do_many_bdg_w_address_and_point(guesses)
        guesses = cls._add_finished_step(cls.STEP_GEOCODE_ADDRESS, guesses)

        # Third try : geocode name with OSM
        guesses = cls._do_many_geocode_name_and_point(guesses)
        guesses = cls._add_finished_step(cls.STEP_GEOCODE_NAME, guesses)

        return guesses

    @staticmethod
    def _add_finished_step(step: str, guesses: dict) -> dict:
        for guess in guesses.values():
            if step not in guess["finished_steps"]:
                guess["finished_steps"].append(step)
        return guesses

    @classmethod
    def _do_many_geocode_name_and_point(cls, guesses: dict) -> dict:
        for guess in guesses.values():
            if cls._need_to_do_step(cls.STEP_GEOCODE_NAME, guess):
                time.sleep(0.800)  # throttle the requests
                guess = cls._do_one_geocode_name_and_point(guess)

                guesses[guess["row"]["ext_id"]] = guess

        return guesses

    @classmethod
    def _do_many_bdg_w_address_and_point(cls, guesses: dict) -> dict:
        for guess in guesses.values():
            if cls._need_to_do_step(cls.STEP_GEOCODE_ADDRESS, guess):
                time.sleep(0.800)
                guess = cls._do_one_bdg_w_address_and_point(guess)
                guesses[guess["row"]["ext_id"]] = guess

        return guesses

    @staticmethod
    def _do_one_bdg_w_address_and_point(guess):
        lat = guess["row"].get("lat", None)
        lng = guess["row"].get("lng", None)
        address = guess["row"].get("address", None)

        if not address or not lat or not lng:
            return guess

        ban_id = _address_to_ban_id(address, lat, lng)

        if ban_id:
            close_bdg_w_ban_id = get_closest(lat, lng, 100).filter(addresses__id=ban_id)

            if close_bdg_w_ban_id.count() == 1:
                guess["match"] = close_bdg_w_ban_id.first()
                guess["match_reason"] = "precise_address_match"

        return guess

    @classmethod
    def _do_one_geocode_name_and_point(cls, guess):
        lat = guess["row"].get("lat", None)
        lng = guess["row"].get("lng", None)
        name = guess["row"].get("name", None)

        if not lat or not lng or not name:
            return guess

        osm_bdg_point = _geocode_name_and_point(name, lat, lng)

        if osm_bdg_point:
            closest_bdgs = get_closest(lat, lng, 20)

            for close_bdg in closest_bdgs:
                if close_bdg.shape.contains(osm_bdg_point):
                    guess["match"] = close_bdg
                    guess["match_reason"] = "found_name_in_osm"
                    return guess

        return guess

    @classmethod
    def _do_many_closest_building(cls, guesses: dict) -> dict:
        tasks = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for guess in guesses.values():
                future = executor.submit(cls._do_one_closest_building, guess)
                future.add_done_callback(lambda future: connections.close_all())
                tasks.append(future)

            for future in concurrent.futures.as_completed(tasks):
                guess = future.result()
                guesses[guess["row"]["ext_id"]] = guess

        return guesses

    @staticmethod
    def _need_to_do_step(step: str, guess: dict) -> bool:
        return step not in guess["finished_steps"] and guess["match"] is None

    @classmethod
    def _do_one_closest_building(cls, guess: dict):
        if not cls._need_to_do_step(cls.STEP_CLOSEST_FROM_POINT, guess):
            return guess

        lat = guess["row"].get("lat", None)
        lng = guess["row"].get("lng", None)

        if not lat or not lng:
            return guess

        # Get the two closest buildings
        closest_bdgs = get_closest(lat, lng, 30)[:2]

        if not closest_bdgs:
            return guess

        first_bdg = closest_bdgs[0]
        # Is the first building within 1 meter ?
        if first_bdg.distance.m <= 1:
            guess["match"] = first_bdg
            guess["match_reason"] = "point_on_bdg"
            return guess

        # Is the first building within 8 meters and the second building is far enough ?
        if first_bdg.distance.m <= 8:
            if len(closest_bdgs) == 1:
                # There is only one building close enough. No need to compare to the second one.
                guess["match"] = first_bdg
                guess["match_reason"] = "isolated_closest_bdg"
                return guess

            if len(closest_bdgs) > 1:
                # There is at least one other close building. We compare the two closest buildings distance to the point.
                second_bdg = closest_bdgs[1]
                min_second_bdg_distance = _min_second_bdg_distance(first_bdg.distance.m)
                if second_bdg.distance.m >= min_second_bdg_distance:
                    guess["match"] = first_bdg
                    guess["match_reason"] = "isolated_closest_bdg"
                    return guess

        # We did not find anything. We return guess as it was sent.
        return guess

    @staticmethod
    def _rows_to_guesses(rows) -> dict:
        guesses = {}
        for row in rows:
            ext_id = row["ext_id"]
            guesses[ext_id] = {
                "row": row,
                "match": None,
                "match_reason": None,
                "finished_steps": [],
            }

        return guesses

    @staticmethod
    def _validate_rows(rows):
        Guesser._validate_types(rows)
        Guesser._validate_ext_ids(rows)

    @staticmethod
    def _validate_types(rows):
        for row in rows:
            if not isinstance(row, dict):
                raise Exception("data must be a list of dicts")

            if "ext_id" not in row:
                raise Exception("ext_id is required for each row")

    @staticmethod
    def _validate_ext_ids(rows):
        ext_ids = [d["ext_id"] for d in rows]
        if len(ext_ids) != len(set(ext_ids)):
            raise Exception("ext_ids are not unique")


def _min_second_bdg_distance(first_bdg_distance: float) -> float:
    # The second building must be at least 10 meters away from the point
    min_distance_floor = 10.0

    # The second building must be at least 3 times the distance of the first building
    ratio = 3
    min_distance_w_ratio = first_bdg_distance * ratio

    return max(min_distance_floor, min_distance_w_ratio)


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
