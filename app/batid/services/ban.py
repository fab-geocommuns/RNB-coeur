import requests


class BanFetcher:
    GEOCODE_URL = "https://api-adresse.data.gouv.fr/search/?q={address}"

    def geocode(self, address):
        url = self.GEOCODE_URL.format(address=address)
        response = requests.get(url)
        geocode_result = response.json()

        return geocode_result
