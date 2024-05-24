import requests

# fonction qui appelle le endpoint de notre API dédié aux recherches par batiment le plus proche
def find_closest_building(lat, lng, radius):
    url = f"https://rnb-api.beta.gouv.fr/api/alpha/buildings/closest/?point={lat},{lng}&radius={radius}"
    r = requests.get(url)

    if r.status_code == 200:
        return url, r.json()
    elif r.status_code == 404:
        return url, None
    else:
        raise Exception("bad request")
