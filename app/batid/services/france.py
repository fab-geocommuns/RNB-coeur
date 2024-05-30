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
    # this function is used in few places and should be replaced with dpts_list()
    metro = {str(i).zfill(2) for i in range(1, 96)}
    metro.add("2A")
    metro.add("2B")
    metro.remove("20")
    outre_mer = set(["971", "972", "973", "974", "976"])
    return metro.union(outre_mer)


def dpt_list_metropole():
    return [
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "17",
        "18",
        "19",
        "2A",
        "2B",
        "21",
        "22",
        "23",
        "24",
        "25",
        "26",
        "27",
        "28",
        "29",
        "30",
        "31",
        "32",
        "33",
        "34",
        "35",
        "36",
        "37",
        "38",
        "39",
        "40",
        "41",
        "42",
        "43",
        "44",
        "45",
        "46",
        "47",
        "48",
        "49",
        "50",
        "51",
        "52",
        "53",
        "54",
        "55",
        "56",
        "57",
        "58",
        "59",
        "60",
        "61",
        "62",
        "63",
        "64",
        "65",
        "66",
        "67",
        "68",
        "69",
        "70",
        "71",
        "72",
        "73",
        "74",
        "75",
        "76",
        "77",
        "78",
        "79",
        "80",
        "81",
        "82",
        "83",
        "84",
        "85",
        "86",
        "87",
        "88",
        "89",
        "90",
        "91",
        "92",
        "93",
        "94",
        "95",
    ]


def dpt_list_overseas():
    return ["971", "972", "973", "974", "975", "976", "977", "978"]


def dpts_list():
    return dpt_list_metropole() + dpt_list_overseas()


# Returns a dict representation of the WGS84 bbox of the metropolitan area
