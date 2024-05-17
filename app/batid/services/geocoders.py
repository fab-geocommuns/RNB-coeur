import requests


class BanGeocoder:
    GEOCODE_URL = "https://api-adresse.data.gouv.fr/search/"
    REVERSE_URL = "https://api-adresse.data.gouv.fr/reverse/?lon={lng}&lat={lat}"

    def geocode(self, params: dict) -> requests.Response:
        # available params are documented here : https://adresse.data.gouv.fr/api-doc/adresse

        response = requests.get(self.GEOCODE_URL, params=params)

        return response

    def reverse(self, lat: float, lng: float) -> requests.Response:
        url = self.REVERSE_URL.format(lat=lat, lng=lng)
        response = requests.get(url)

        return response


class BanBatchGeocoder:

    GEOCODE_URL = "https://api-adresse.data.gouv.fr/search/csv/"

    def geocode(
        self,
        csv_path,
        columns=None,
        result_columns=None,
        citycode_col=None,
        postcode_col=None,
    ):

        with open(csv_path, "rb") as f:

            files = {"data": f}

            # Prepare the form data
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

            # Send POST request
            response = requests.post(self.GEOCODE_URL, files=files, data=data)

            return response


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


class GeocodeEarthGeocoder:
    API_KEY = "ge-9b206ad0e734c565"
    GEOCODE_URL = "https://api.geocode.earth/v1/search"

    def geocode(self, params):
        if "text" not in params:
            raise Exception("Missing 'text' parameter for GeocodeEarth geocoding")

        params["api_key"] = self.API_KEY

        response = requests.get(self.GEOCODE_URL, params=params)

        geocode_result = response.json()

        return geocode_result
