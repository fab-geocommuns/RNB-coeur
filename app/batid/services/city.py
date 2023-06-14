import requests


def fetch_city_geojson(insee_code: int) -> dict:
    url = f"https://geo.api.gouv.fr/communes?code={insee_code}&format=geojson&geometry=contour"
    return requests.get(url).json()


# todo : rename into fetch_dpt_cities_geojson
def fetch_dpt_cities_geojson(dpt: str) -> dict:
    url = f"https://geo.api.gouv.fr/departements/{dpt}/communes?format=geojson&geometry=contour"
    return requests.get(url).json()
