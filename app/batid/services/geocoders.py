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
