import concurrent.futures
import csv
import json
import re
import time
from abc import ABC
from abc import abstractmethod
from io import StringIO
from typing import Callable
from typing import Optional
from typing import TypedDict

import orjson
import pandas as pd
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.db import connection
from tqdm.notebook import tqdm

from batid.models import Building
from batid.services.closest_bdg import get_closest_from_point
from batid.services.closest_bdg import get_closest_from_poly
from batid.services.geocoders import BanBatchGeocoder
from batid.services.geocoders import BanGeocoder
from batid.services.geocoders import PhotonGeocoder
from batid.utils.misc import max_by_group


class Input(TypedDict):
    ext_id: str
    polygon: Polygon
    lat: float
    lng: float
    name: str
    address: str
    ban_id: str


class Guess(TypedDict):
    input: Input
    matches: list[str]
    match_reason: str
    finished_steps: list[str]


class Guesser:
    def __init__(self, batch_size: int = 5000):
        self.guesses: dict[str, Guess] = {}
        self.handlers: list[AbstractHandler] = [
            ClosestFromPointHandler(),
            GeocodeAddressHandler(),
            GeocodeNameHandler(),
        ]
        self.batch_size = batch_size

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
        self.guess_all(
            skip_if_no_change=True,
            on_batch_done=lambda: self.save_work_file(file_path),
        )

    def guess_all(
        self,
        skip_if_no_change: bool = False,
        on_batch_done: Optional[Callable] = None,
    ):
        batches = self._guesses_to_batches()

        progress_bar = tqdm(batches)
        for batch in progress_bar:
            batch, changed_batch = self.guess_batch(batch)

            if not changed_batch and skip_if_no_change:
                progress_bar.set_description("Batch already processed, skipping")
                continue

            self.guesses.update(batch)
            progress_bar.set_description("Batch processed")
            if on_batch_done:
                on_batch_done()

    def _guesses_to_batches(self) -> list[dict[str, Guess]]:
        batches = []
        batch = {}
        last_ext_id = list(self.guesses.keys())[-1]

        for ext_id, guess in self.guesses.items():
            batch[ext_id] = guess

            if len(batch) == self.batch_size or ext_id == last_ext_id:
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
        match_count = df["match_reason"].notnull().sum()
        match_percentage = match_count / total * 100
        print(f"Number of match: {match_count} ({match_percentage:.2f}%)")

        # Count empty finished_steps
        print("\n-- finished_steps --")

        for idx, handler in enumerate(self.handlers):
            finished_steps_count = (
                df["finished_steps"].apply(lambda x: handler.name in x).sum()
            )
            finished_steps_percentage = finished_steps_count / total * 100
            print(
                f"Rows with finished_steps {handler.name}: {finished_steps_count} ({finished_steps_percentage:.2f}%)"
            )

        empty_finished_steps = df["finished_steps"].apply(lambda x: len(x) == 0).sum()
        empty_finished_steps_percentage = empty_finished_steps / total * 100
        print(
            f"Rows with empty finished_steps: {empty_finished_steps} ({empty_finished_steps_percentage:.2f}%)"
        )

        # Display table of all march_reason values with their absolute count and their percentage
        match_reason_count = df["match_reason"].value_counts()
        match_reason_percentage = match_reason_count / total * 100
        print("\n-- match_reasons : absolute --")
        print(match_reason_count)
        print("\n-- match_reasons : % --")
        print(match_reason_percentage)

        # About inputs
        print("\n-- Inputs --")

        # how many have an input_ban_id
        if "input_ban_id" in df.columns:
            ban_id_count = df["input_ban_id"].notnull().sum()
            ban_id_percentage = ban_id_count / total * 100
            print(f"rows with ban_id: {ban_id_count} ({ban_id_percentage:.2f}%)")

    def display_matched_sample(
        self,
        match_reason: str,
        sample_size: int = 10,
        sample_cols: list = ["input_ext_id", "matches", "match_reason"],
    ):

        data = self.matched_sample(match_reason, sample_size, sample_cols)

        print(data)

    def matched_sample(
        self,
        match_reason: str,
        sample_size: int = 10,
        sample_cols: list = ["input_ext_id", "matches", "match_reason"],
    ):
        data = list(self.guesses.values())

        df = pd.json_normalize(data, sep="_")

        reasons = df[df["match_reason"] == match_reason]

        return reasons[sample_cols].sample(sample_size)

    def unmatched_sample(self, sample_size: int = 10):
        data = list(self.guesses.values())

        df = pd.json_normalize(data, sep="_")

        unmatched = df[df["match_rnb_id"].isnull()]
        unmatched = unmatched[["input_ext_id"]]

        print(unmatched.sample(sample_size))

    def display_unmatched(self, count: int = 10):

        data = list(self.guesses.values())

        df = pd.json_normalize(data, sep="_")

        # unmatched is where "matches" is empty or null
        unmatched = df[
            df["matches"].isnull() | df["matches"].apply(lambda x: len(x) == 0)
        ]

        print(unmatched.sample(count))

    def save_work_file(self, file_path):
        self.convert_matches()

        with open(file_path, "wb") as f:
            f.write(orjson.dumps(self.guesses, option=orjson.OPT_INDENT_2))

    def convert_matches(self):
        for ext_id, guess in self.guesses.items():

            rnb_ids = []

            for idx, match in enumerate(guess["matches"]):
                if isinstance(match, Building):
                    rnb_ids.append(match.rnb_id)
                if isinstance(match, str):
                    rnb_ids.append(match)

            guess["matches"] = rnb_ids

    def guess_batch(self, guesses: dict) -> tuple:
        guesses_changed = False
        for handler in self.handlers:
            if not isinstance(handler, AbstractHandler):
                raise ValueError("Handler must be an instance of AbstractHandler")

            guesses, handler_changed_guesses = handler.handle(guesses)

            if handler_changed_guesses:
                guesses_changed = True

        return guesses, guesses_changed

    def to_csv(self, file_path, ext_id_col_name="ext_id", one_rnb_id_per_row=False):

        self.convert_matches()

        rnb_id_col_name = "rnb_id" if one_rnb_id_per_row else "rnb_ids"

        rows = []
        for ext_id, guess in self.guesses.items():

            matches = guess.get("matches", None)
            reason = guess.get("match_reason", None)

            # Matches is empty
            if len(matches) == 0:

                rows.append(
                    {
                        ext_id_col_name: ext_id,
                        rnb_id_col_name: "" if one_rnb_id_per_row else [],
                        "match_reason": reason,
                    }
                )

            else:

                # Matches is not empty
                if one_rnb_id_per_row:
                    for match in matches:
                        rows.append(
                            {
                                ext_id_col_name: ext_id,
                                rnb_id_col_name: match,
                                "match_reason": reason,
                            }
                        )
                else:
                    rows.append(
                        {
                            ext_id_col_name: ext_id,
                            rnb_id_col_name: matches,
                            "match_reason": reason,
                        }
                    )

        with open(file_path, "w") as f:
            writer = csv.DictWriter(
                f, fieldnames=[ext_id_col_name, rnb_id_col_name, "match_reason"]
            )
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _inputs_to_guesses(inputs) -> dict:
        guesses = {}
        for input in inputs:
            # Always transform ext_id to string
            ext_id = str(input["ext_id"])
            input["ext_id"] = ext_id

            guesses[ext_id] = {
                "input": input,
                "matches": [],
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

            if "polygon" in input and not isinstance(input["polygon"], dict):
                raise Exception("polygon must be a geojson geometry formatted dict")

    @staticmethod
    def _validate_ext_ids(inputs):
        ext_ids = [d["ext_id"] for d in inputs]
        if len(ext_ids) != len(set(ext_ids)):
            raise Exception("ext_ids are not unique")


class AbstractHandler(ABC):
    _name = None

    def handle(self, guesses: dict[str, Guess]) -> tuple[dict[str, Guess], bool]:
        handler_changed_guesses = False
        to_guess, to_not_guess = self._split_guesses(guesses)

        if len(to_guess) > 0:
            handler_changed_guesses = True
            to_guess = self._guess_batch(to_guess)

            guesses = to_guess | to_not_guess
            guesses = self._add_finished_step(guesses)

        return guesses, handler_changed_guesses

    def _split_guesses(self, guesses: dict) -> tuple:
        to_handle = {}
        not_to_handle = {}

        for ext_id, guess in guesses.items():

            if self.name not in guess["finished_steps"] and len(guess["matches"]) == 0:
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

    def _add_finished_step(self, guesses: dict[str, Guess]) -> dict[str, Guess]:
        for guess in guesses.values():
            if self.name not in guess["finished_steps"]:
                guess["finished_steps"].append(self.name)

        return guesses


class ClosestFromPointHandler(AbstractHandler):
    _name = "closest_from_point"

    def __init__(self, closest_radius=30, isolated_bdg_max_distance=8):
        self.closest_radius = closest_radius
        self.isolated_bdg_max_distance = isolated_bdg_max_distance

    def _guess_batch(self, guesses: dict[str, Guess]) -> dict[str, Guess]:
        tasks = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for guess in guesses.values():
                future = executor.submit(self._guess_one, guess)
                # We comment out the line below since closing all connections might provoke with open connection where the query is not yet executed
                # future.add_done_callback(lambda future: connections.close_all())
                tasks.append(future)

            for future in concurrent.futures.as_completed(tasks):
                guess = future.result()
                guesses[guess["input"]["ext_id"]] = guess

        return guesses

    def _guess_one(self, guess: Guess) -> Guess:
        lat = guess["input"].get("lat", None)
        lng = guess["input"].get("lng", None)

        if not lat or not lng:
            return guess

        result = self.__class__.guess_closest_building(
            lat, lng, self.closest_radius, self.isolated_bdg_max_distance
        )

        if result:
            match, reason = result
            guess["matches"].append(match)
            guess["match_reason"] = reason

        return guess

    @staticmethod
    def guess_closest_building(
        lat: float, lng: float, closest_radius: int = 30, isolated_max_distance: int = 8
    ) -> Optional[tuple[Building, str]]:
        # Get the two closest buildings
        closest_bdgs = get_closest_from_point(lat, lng, closest_radius)[:2]
        # We have to close the connection to avoid a "too many connections" error
        connection.close()

        if not closest_bdgs:
            return None

        first_bdg = closest_bdgs[0]

        # Is the the point is in the first building?
        if first_bdg.distance.m <= 0:
            return first_bdg, "point_on_bdg"

        # Is the first building is too far from the point anyway?
        if first_bdg.distance.m > isolated_max_distance:
            return None

        # There is only one building close enough. No need to compare to the second one.
        if len(closest_bdgs) == 1:
            return first_bdg, "isolated_closest_bdg"

        # There is at least one other close building. We compare the two closest buildings distance to the point.
        second_bdg = closest_bdgs[1]
        min_second_bdg_distance = ClosestFromPointHandler._min_second_bdg_distance(
            first_bdg.distance.m
        )
        if second_bdg.distance.m >= min_second_bdg_distance:
            return first_bdg, "isolated_closest_bdg"

        return None

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

    def __init__(self, closest_radius=100, min_score=0.8):
        self.closest_radius = closest_radius
        self.min_score = min_score

    def _guess_batch(self, guesses: dict[str, Guess]) -> dict[str, Guess]:

        guesses = self._geocode_batch(guesses)

        for guess in guesses.values():
            guess = self._guess_one(guess)
            guesses[guess["input"]["ext_id"]] = guess

        return guesses

    def _guess_one(self, guess: Guess) -> Guess:
        lat = guess["input"].get("lat", None)
        lng = guess["input"].get("lng", None)
        ban_id = guess["input"].get("ban_id", None)

        if not ban_id:
            return guess

        if lat and lng:
            qs = get_closest_from_point(lat, lng, self.closest_radius)
        else:
            qs = Building.objects.all()

        # The old version of the query before the "bdg_addresses_id_idx" index disappeared
        # bdgs = qs.filter(addresses_id__contains=[ban_id])
        bdgs = qs.filter(addresses_read_only__id=ban_id)

        if bdgs.count() > 0:
            guess["matches"] = bdgs
            guess["match_reason"] = "precise_address_match"

        return guess

    def _geocode_batch(self, guesses: dict[str, Guess]) -> dict[str, Guess]:

        # Format addresses for geocoding
        addresses = []
        for ext_id, guess in guesses.items():
            address = guess["input"].get("address", None)

            if address:
                address = self._clean_address(address)
                addresses.append(
                    {
                        "ext_id": ext_id,
                        "address": address,
                    }
                )

        if not addresses:
            return guesses

        # Geocode addresses in batch
        geocoder = BanBatchGeocoder()
        response = geocoder.geocode(
            addresses,
            columns=["address"],
            result_columns=["result_type", "result_id", "result_score"],
        )
        if response.status_code == 400:
            with open("error_addresses.txt", "w") as f:
                f.write("\n".join([address["address"] for address in addresses]))
            raise Exception(f"Error while geocoding addresses : {response.text}")
        if response.status_code != 200:
            raise Exception(f"Error while geocoding addresses : {response.text}")

        # Parse the response
        csv_file = StringIO(response.text)
        reader = csv.DictReader(csv_file)

        address_results = [row for row in reader if row["result_type"] == "housenumber"]

        # Get max scoring address for each input row
        address_result_with_max_score_by_ext_id = max_by_group(
            address_results,
            max_key=lambda x: float(x["result_score"]),
            group_key=lambda x: x["ext_id"],
        )

        # Augment input guess with resulting ban_id
        for ext_id, address_result in address_result_with_max_score_by_ext_id.items():
            if float(address_result["result_score"]) >= self.min_score:
                guesses[ext_id]["input"]["ban_id"] = address_result["result_id"]

        return guesses

    @staticmethod
    def _clean_address(address: str) -> str:

        # Remove any newline in the middle of the adresse
        address = address.replace("\n", " ").strip()

        # Transform any multiple space into single space
        address = re.sub(r"\s+", " ", address)

        # Remove any comma or space or both at the start of the address
        address = address.lstrip(",. ")

        return address

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
            return None

        geo_results = geocode_response.json()

        if "features" in geo_results and geo_results["features"]:
            best = geo_results["features"][0]

            if best["properties"]["score"] >= 0.8:
                return best["properties"]["id"]

        return None


class GeocodeNameHandler(AbstractHandler):
    _name = "geocode_name"

    # We allow to geocode a name in a square bounding box around a point.
    # The "apothem" is the radius of the inscribed circle of this square
    # (i.e. the "radius" of the bounding box around the point).
    def __init__(self, sleep_time=0, bbox_apothem_in_meters=5000, photon_url=None):
        self.sleep_time = sleep_time
        self.bbox_apothem_in_meters = bbox_apothem_in_meters
        if photon_url:
            PhotonGeocoder.GEOCODE_URL = photon_url

    def _guess_batch(self, guesses: dict[str, Guess]) -> dict[str, Guess]:

        if self.sleep_time > 0:

            # We need to avoid throttling. We do one by one.
            for guess in guesses.values():
                guess = self._guess_one(guess)
                guesses[guess["input"]["ext_id"]] = guess
        else:

            # No need to avoid throttling. We can parallelize.
            tasks = []

            with concurrent.futures.ThreadPoolExecutor() as executor:
                for guess in guesses.values():
                    future = executor.submit(self._guess_one, guess)
                    # We comment out the line below since closing all connections might provoke with open connection where the query is not yet executed
                    # future.add_done_callback(lambda future: connections.close_all())
                    tasks.append(future)

                for future in concurrent.futures.as_completed(tasks):
                    guess = future.result()
                    guesses[guess["input"]["ext_id"]] = guess

        return guesses

    def _guess_one(self, guess: Guess) -> Guess:

        lat = guess["input"].get("lat", None)
        lng = guess["input"].get("lng", None)
        name = guess["input"].get("name", None)

        if not lat or not lng or not name:
            return guess

        # We sleep a little bit to avoid being throttled by the geocoder
        time.sleep(self.sleep_time)

        osm_bdg_point = self._geocode_name_and_point(
            name, lat, lng, self.bbox_apothem_in_meters
        )

        if osm_bdg_point:
            result = ClosestFromPointHandler.guess_closest_building(
                osm_bdg_point.y, osm_bdg_point.x
            )

            if result:
                bdg, reason = result
                guess["matches"].append(bdg)
                guess["match_reason"] = f"found_name_in_osm_{reason}"
                return guess

        return guess

    @staticmethod
    def _geocode_name_and_point(
        name: str, lat: float, lng: float, bbox_apothem_in_meters: int
    ) -> Optional[Point]:
        bbox = GeocodeNameHandler.lng_lat_bbox_around_point(
            lat, lng, bbox_apothem_in_meters
        )
        geocode_params = {
            "q": name,
            "lat": lat,
            "lon": lng,
            "lang": "fr",
            "limit": 1,
            "bbox": ",".join(map(str, bbox)),
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
            return None

    @staticmethod
    def lng_lat_bbox_around_point(
        lat: float, lng: float, bbox_apothem_in_meters: int
    ) -> list[float]:
        point = Point(lng, lat, srid=4326)
        point.transform(3857)
        bounding_circle = point.buffer(bbox_apothem_in_meters)
        envelope = bounding_circle.envelope
        envelope.transform(4326)
        return list(envelope.extent)


class PartialRoofHandler(AbstractHandler):
    """
    This handler is used to match a building based on a roof section.
    """

    _name = "partial_roof"

    def __init__(self, isolated_section_max_distance=1, min_second_bdg_distance=6):
        self.isolated_section_max_distance = isolated_section_max_distance
        self.min_second_bdg_distance = min_second_bdg_distance

    def _guess_batch(self, guesses: dict[str, Guess]) -> dict[str, Guess]:
        tasks = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            for guess in guesses.values():
                future = executor.submit(self._guess_one, guess)
                # We comment out the line below since closing all connections might provoke with open connection where the query is not yet executed
                # future.add_done_callback(lambda future: connections.close_all())
                tasks.append(future)

            for future in concurrent.futures.as_completed(tasks):
                guess = future.result()
                guesses[guess["input"]["ext_id"]] = guess

        return guesses

    def _guess_one(self, guess: Guess) -> Guess:
        roof_geojson = guess["input"].get("polygon", None)

        if not roof_geojson:
            return guess

        roof_poly = GEOSGeometry(json.dumps(roof_geojson))
        # we close the connection to avoid a "too many connections" error due to multi threading
        connection.close()

        # Get closest buildings. We have to get many
        closest_bdgs = get_closest_from_poly(roof_poly, 35)[:20]

        if not closest_bdgs:
            return guess

        # Est-ce qu'il y a un seul batiment qui couvre à plus de X% le pan de toit ?
        sole_bdg_intersecting_enough = self._roof_interesected_enough_by_one_bdg(
            roof_poly, closest_bdgs
        )
        if isinstance(sole_bdg_intersecting_enough, Building):
            guess["matches"].append(sole_bdg_intersecting_enough)
            guess["match_reason"] = "sole_bdg_intersects_roof_enough"
            return guess

        # Est-ce qu'il y a unn seul bâtiment qui intersecte et le second bâtiment le plus proche est assez loin ?
        if self._isolated_bdg_intersecting(roof_poly, closest_bdgs):
            guess["matches"].append(closest_bdgs[0])
            guess["match_reason"] = "isolated_bdg_intersects_roof"
            return guess

        bdgs_covered_enough = self._many_bdgs_covered_enough(roof_poly, closest_bdgs)
        if bdgs_covered_enough:
            guess["matches"] = bdgs_covered_enough
            guess["match_reason"] = "many_bdgs_covered_enough_by_roof"
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

        return False

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
