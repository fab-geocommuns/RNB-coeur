import csv
from io import StringIO
from uuid import UUID

import requests
from batid.exceptions import BANAPIDown
from batid.exceptions import BANInvalidResponse
from requests import Response


class BanGeocoder:
    GEOCODE_URL = "https://data.geopf.fr/geocodage/search/"
    REVERSE_URL = "https://data.geopf.fr/geocodage/reverse/?lon={lng}&lat={lat}"

    def geocode(self, params: dict) -> requests.Response:
        # available params are documented here : https://adresse.data.gouv.fr/api-doc/adresse

        response = requests.get(self.GEOCODE_URL, params=params)

        if response.status_code == 200:
            return response
        else:
            raise BANAPIDown

    def reverse(self, lat: float, lng: float) -> requests.Response:
        url = self.REVERSE_URL.format(lat=lat, lng=lng)
        response = requests.get(url)

        return response

    def cle_interop_ban_best_result(self, params: dict):
        response = self.geocode(params)
        results = response.json()

        if "features" in results and results["features"]:
            best = results["features"][0]

            if best["properties"]["type"] == "housenumber":
                return {
                    "cle_interop_ban": best["properties"]["id"],
                    # banId is not provided for every address
                    "ban_id": self._parse_ban_id(best["properties"].get("banId")),
                    "score": best["properties"]["score"],
                }

        return {"cle_interop_ban": None, "ban_id": None, "score": None}

    @staticmethod
    def _parse_ban_id(ban_id) -> UUID | None:
        """
        Convert the banId sent by the BAN. A value which is not a UUID is a BAN
        error: it is raised, not silently treated as absent.
        """
        if ban_id is None:
            return None
        try:
            return UUID(str(ban_id))
        except ValueError as error:
            raise BANInvalidResponse(f"banId {ban_id!r} is not a UUID") from error


class BanBatchGeocoder:

    GEOCODE_URL = "https://data.geopf.fr/geocodage/search/csv/"

    def geocode_file(
        self,
        csv_path,
        columns=None,
        result_columns=None,
        citycode_col=None,
        postcode_col=None,
    ) -> Response:

        with open(csv_path, "rb") as f:

            files = {"data": f}

            # Prepare the form data
            data = self._form_data(columns, result_columns, citycode_col, postcode_col)

            # Send POST request
            return requests.post(self.GEOCODE_URL, files=files, data=data)

    def geocode(
        self,
        data,
        columns=None,
        result_columns=None,
        citycode_col=None,
        postcode_col=None,
    ) -> Response:

        # Create an in-memory CSV file
        csv_buffer = StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        csv_buffer.seek(0)

        # Prepare the file data payload
        files = {"data": ("data.csv", csv_buffer.getvalue(), "text/csv")}

        # Prepare the form data
        data = self._form_data(columns, result_columns, citycode_col, postcode_col)

        # Send POST request
        response = requests.post(self.GEOCODE_URL, files=files, data=data)

        return response

    def _form_data(self, columns, result_columns, citycode_col, postcode_col):
        data = {}
        if columns:
            for column in columns:
                data.setdefault("columns", []).append(column)

        if result_columns:
            for result_column in result_columns:
                data.setdefault("result_columns", []).append(result_column)

        if citycode_col:
            data["citycode"] = citycode_col
        if postcode_col:
            data["postcode"] = postcode_col

        return data


class PhotonGeocoder:
    GEOCODE_URL = "https://photon.komoot.io/api/"

    def geocode(self, params) -> requests.Response:
        if "q" not in params:
            raise Exception("Missing 'q' parameter for Photon geocoding")

        response = requests.get(self.GEOCODE_URL, params=params)

        return response


class NominatimGeocoder:
    GEOCODE_URL = "https://nominatim.openstreetmap.org/search"

    def geocode(self, params):
        if "format" not in params:
            params["format"] = "geocodejson"

        response = requests.get(self.GEOCODE_URL, params=params)

        geocode_result = response.json()

        return geocode_result
