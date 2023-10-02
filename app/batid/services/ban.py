import requests


class BanFetcher:
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
