import concurrent
import time
from typing import Optional
from django.contrib.gis.geos import Point
from batid.services.closest_bdg import get_closest
from batid.services.geocoders import PhotonGeocoder


def guess_all(rows):
    _validate_rows(rows)
    guesses = _rows_to_guesses(rows)

    found_w_closest, not_found_so_far = _do_many_closest_building(guesses)
    found_w_geocode, not_found_so_far = _do_many_geocode_name_and_point(
        not_found_so_far
    )

    all = found_w_closest + found_w_geocode + not_found_so_far

    return all


def _do_many_geocode_name_and_point(guesses: list) -> (list, list):
    found = []
    not_found = []

    for guess in guesses:
        time.sleep(0.800)  # we have to throttle the requests to the geocoding service
        guess = _do_one_geocode_name_and_point(guess)

        if guess["match"]:
            found.append(guess)
        else:
            not_found.append(guess)

    return found, not_found


def _do_one_geocode_name_and_point(guess):
    lat = guess["row"].get("lat", None)
    lng = guess["row"].get("lng", None)
    name = guess["row"].get("name", None)

    if not lat or not lng or not name:
        return guess

    osm_bdg_point = _geocode_name_and_point(name, lat, lng)

    if osm_bdg_point:
        closest_bdg = get_closest(osm_bdg_point[1], osm_bdg_point[0], 1)[:1]

        if closest_bdg:
            guess["match"] = closest_bdg[0]
            guess["matched_on_step"] = "geocode_name_and_point"
            return guess

    return guess


# todo : à tester
def _do_many_closest_building(guesses: list) -> (list, list):
    found = []
    not_found = []

    with concurrent.futures.ThreadPoolExecutor() as executor:
        tasks = [executor.submit(_do_one_closest_building, guess) for guess in guesses]
        for future in concurrent.futures.as_completed(tasks):
            guess = future.result()
            if guess["match"]:
                found.append(guess)
            else:
                not_found.append(guess)

    return found, not_found


def _do_one_closest_building(guess):
    lat = guess["row"].get("lat", None)
    lng = guess["row"].get("lng", None)

    if not lat or not lng:
        return guess

    # Get the two closest buildings
    closest_bdgs = get_closest(lat, lng, 20)[:2]

    if not closest_bdgs:
        return guess

    first_bdg = closest_bdgs[0]
    # Is the first building within 1 meter ?
    if first_bdg.distance.m <= 1:
        guess["match"] = first_bdg
        guess["matched_on_step"] = "point_on_bdg"
        return guess

    # Is the first building within 5 meters and the second building is far enough ?
    if first_bdg.distance.m <= 5 and len(closest_bdgs) > 1:
        second_bdg = closest_bdgs[1]
        min_second_bdg_distance = _min_second_bdg_distance(first_bdg.distance.m)
        if second_bdg.distance.m >= min_second_bdg_distance:
            guess["match"] = first_bdg
            guess["matched_on_step"] = "point_close_enough"
            return guess

    # We did not find anything. We return guess as it was sent.
    return guess


def _rows_to_guesses(rows):
    guesses = []
    for row in rows:
        guesses.append({"row": row, "match": None, "matched_on_step": None})

    return guesses


def _validate_rows(rows):
    _validate_types(rows)
    _validate_ext_ids(rows)


def _validate_types(rows):
    for row in rows:
        if not isinstance(row, dict):
            raise Exception("data must be a list of dicts")

        if "ext_id" not in row:
            raise Exception("ext_id is required for each row")


def _validate_ext_ids(rows):
    ext_ids = [d["ext_id"] for d in rows]
    if len(ext_ids) != len(set(ext_ids)):
        raise Exception("ext_ids are not unique")


def _min_second_bdg_distance(first_bdg_distance: float) -> float:
    # The formula has been built here : https://chat.openai.com/share/116eeabc-9ba0-4b2e-902f-2291277ef879
    ratio = 1.82 ** (-0.202 * first_bdg_distance) + 1.3
    return first_bdg_distance * ratio


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