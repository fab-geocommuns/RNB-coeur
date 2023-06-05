import requests


def get_city_geojson(insee_code: int) -> dict:
    url = f"https://geo.api.gouv.fr/communes?code={insee_code}&format=geojson&geometry=contour"
    return requests.get(url).json()


def get_dpt_cities_geojson(dpt: str) -> dict:
    url = f"https://geo.api.gouv.fr/departements/{dpt}/communes?format=geojson&geometry=contour"
    return requests.get(url).json()
