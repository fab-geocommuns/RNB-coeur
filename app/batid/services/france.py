import requests


def fetch_city_geojson(insee_code: int) -> dict:
    url = f"https://geo.api.gouv.fr/communes?code={insee_code}&format=geojson&geometry=contour"
    return requests.get(url).json()


def fetch_dpt_cities_geojson(dpt: str) -> dict:
    url = f"https://geo.api.gouv.fr/departements/{dpt}/communes?format=geojson&geometry=contour"
    return requests.get(url).json()


def fetch_departments_refs() -> dict:
    url = "https://geo.api.gouv.fr/departements"
    return requests.get(url).json()


def dpt_codes() -> set:
    metro = {str(i).zfill(2) for i in range(1, 96)}
    metro.add("2A")
    metro.add("2B")
    metro.remove("20")
    outre_mer = set(["971", "972", "973", "974", "976"])
    return metro.union(outre_mer)


# Returns a dict representation of the WGS84 bbox of the metropolitan area
