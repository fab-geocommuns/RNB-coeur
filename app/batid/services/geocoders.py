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


class NominatimGeocoder:
    GEOCODE_URL = "https://nominatim.openstreetmap.org/search"

    def geocode(self, params):
        if "q" not in params:
            raise Exception("Missing 'q' parameter for OSM geocoding")

        if "format" not in params:
            params["format"] = "geocodejson"

        response = requests.get(self.GEOCODE_URL, params=params)

        geocode_result = response.json()

        return geocode_result

    @staticmethod
    def prepare_name_string(name: str) -> str:
        # remove a list of generic words in the name
        generic_words = [
            "magasin",
        ]

        for w in generic_words:
            name = name.replace(w, "")
            name = name.replace(w.upper(), "")

        return name
