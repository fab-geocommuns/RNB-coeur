import requests


class BanGeocoder:
    GEOCODE_URL = "https://api-adresse.data.gouv.fr/search/?q={address}"
    REVERSE_URL = "https://api-adresse.data.gouv.fr/reverse/?lon={lng}&lat={lat}"

    def geocode(self, address):
        url = self.GEOCODE_URL.format(address=address)
        response = requests.get(url)
        geocode_result = response.json()

        return geocode_result

    def reverse(self, lat: float, lng: float):
        url = self.REVERSE_URL.format(lat=lat, lng=lng)
        response = requests.get(url)
        reverse_result = response.json()

        return reverse_result


class PhotonGeocoder:
    GEOCODE_URL = "https://photon.komoot.io/api/"

    def geocode(self, params):
        if "q" not in params:
            raise Exception("Missing 'q' parameter for Photon geocoding")

        response = requests.get(self.GEOCODE_URL, params=params)

        return response.json()


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
