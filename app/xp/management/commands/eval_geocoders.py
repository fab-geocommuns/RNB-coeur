from pprint import pprint
from typing import Optional
from django.core.management.base import BaseCommand
import json
from batid.models import Plot
from batid.services.geocoders import (
    GeocodeEarthGeocoder,
    NominatimGeocoder,
    PhotonGeocoder,
    BanGeocoder,
)
from batid.services.imports.import_plots import import_etalab_plots
from batid.services.guess_bdg import BuildingGuess

from django.contrib.gis.geos import GEOSGeometry, Point

import pandas as pd


class Command(BaseCommand):
    TESTS = [
        {
            "address": "1, LOTISSEMENT LE PARC DU SEUIL, 38660 sainte-marie d'alloix",
            "name": "SALLE POLYVALENTE (NOUVELLE)",
            "poly_coords": [
                [
                    [5.967772650205347, 45.37982517372984],
                    [5.967602656998906, 45.37960947602079],
                    [5.968101669313739, 45.37940340690545],
                    [5.968326499036749, 45.37964606765428],
                    [5.967772650205347, 45.37982517372984],
                ]
            ],
        },
        {
            "address": "24 allée victor basch, 94170 le perreux sur mane",
            "name": None,
            "poly_coords": [
                [
                    [2.500403508506764, 48.84497821828376],
                    [2.5001769226883255, 48.844873434092136],
                    [2.5001417100274352, 48.8447827552873],
                    [2.5002075423934684, 48.84463061603577],
                    [2.5005566070318253, 48.84470215176765],
                    [2.500645404177419, 48.844730363014406],
                    [2.500403508506764, 48.84497821828376],
                ]
            ],
        },
        {
            "address": "344 RUE DES ALLOBROGES, 38200 Luzinay",
            "name": None,
            "poly_coords": [
                [
                    [4.948760120153054, 45.58886574132006],
                    [4.948688536594574, 45.5883870601358],
                    [4.949218785169961, 45.58830356881356],
                    [4.949194923984294, 45.5880252635084],
                    [4.949672147700653, 45.58796774690694],
                    [4.9498047098452105, 45.58880080418956],
                    [4.948760120153054, 45.58886574132006],
                ]
            ],
        },
        {
            "address": "344 RUE DES ALLOBROGES, 38200 Luzinay",
            "name": "GS PAUL GERMAIN, GARDERIE ET CENTRE DE LOISIRS",
            "poly_coords": [
                [
                    [4.948760120153054, 45.58886574132006],
                    [4.948688536594574, 45.5883870601358],
                    [4.949218785169961, 45.58830356881356],
                    [4.949194923984294, 45.5880252635084],
                    [4.949672147700653, 45.58796774690694],
                    [4.9498047098452105, 45.58880080418956],
                    [4.948760120153054, 45.58886574132006],
                ]
            ],
        },
        {
            "address": "52 bis avenue de moutille, cénac",
            "name": None,
            "poly_coords": [
                [
                    [-0.453340083344699, 44.77767473510235],
                    [-0.45325277400871755, 44.777644420689654],
                    [-0.4532328447039049, 44.77771784890655],
                    [-0.4531749548171433, 44.77771178602981],
                    [-0.45316546467267926, 44.777744795017924],
                    [-0.45312750409178193, 44.77774075310205],
                    [-0.45307530829316534, 44.77784651647505],
                    [-0.4531502804401555, 44.777874809828404],
                    [-0.4531132688740911, 44.7779569952051],
                    [-0.4534729453773707, 44.778016276388456],
                    [-0.45356310175691306, 44.77784382186903],
                    [-0.45327839740056675, 44.77778723511818],
                    [-0.453340083344699, 44.77767473510235],
                ]
            ],
        },
        {
            "address": "32 Rue de Comboire, 38130 Échirolles",
            "name": "neway 38",
            "poly_coords": [
                [
                    [5.6900094089762945, 45.14356328049914],
                    [5.689776694658207, 45.1434798861992],
                    [5.689896805273776, 45.1433011837172],
                    [5.690146410147065, 45.14339384433379],
                    [5.6900094089762945, 45.14356328049914],
                ]
            ],
        },
        {
            "address": "32 Rue de Comboire, 38130 Échirolles",
            "name": "neway",
            "poly_coords": [
                [
                    [5.6900094089762945, 45.14356328049914],
                    [5.689776694658207, 45.1434798861992],
                    [5.689896805273776, 45.1433011837172],
                    [5.690146410147065, 45.14339384433379],
                    [5.6900094089762945, 45.14356328049914],
                ]
            ],
        },
        {
            "address": "Rue de Comboire, 38130 Échirolles",
            "name": "magasin neway 32",
            "poly_coords": [
                [
                    [5.6900094089762945, 45.14356328049914],
                    [5.689776694658207, 45.1434798861992],
                    [5.689896805273776, 45.1433011837172],
                    [5.690146410147065, 45.14339384433379],
                    [5.6900094089762945, 45.14356328049914],
                ]
            ],
        },
        {
            "address": None,
            "name": "notre dame de paris",
            "poly_coords": [
                [
                    [2.349150087694966, 48.85359894475607],
                    [2.3485998949495865, 48.853090787430745],
                    [2.349594280002691, 48.85244644981117],
                    [2.350558379216835, 48.85227041798822],
                    [2.350992476245267, 48.85297454156594],
                    [2.349150087694966, 48.85359894475607],
                ]
            ],
        },
        {
            "address": "136 route de la Bourbre à Saint-Jean De Soudain",
            "name": "intermarché",
            "poly_coords": [
                [
                    [5.428925286271749, 45.566720827797894],
                    [5.428695952521991, 45.566866394346334],
                    [5.428503312165418, 45.56586454623232],
                    [5.429631634253582, 45.56596301927462],
                    [5.429916008105522, 45.566194216190866],
                    [5.429622460895473, 45.56675293810241],
                    [5.428925286271749, 45.566720827797894],
                ]
            ],
        },
    ]

    def handle(self, *args, **options):
        r = self.geocode()
        r = self.evaluate(r)
        self.report(r)

    def get_geocoders_fns(self):
        return {
            "nominatim": self.nominatim_point,
            "photon": self.photon_point,
            "geocode_earth": self.geocode_earth_point,
            # "addok_ban": self.geocode_ban_point
        }

    def report(self, tests):
        ##########
        # Number of good results
        ##########

        parsed_data = {
            f"{item['name']} // {item['address']}": {
                geocoder: result["valid"]
                for geocoder, result in item["geocoding"].items()
            }
            for item in tests
        }

        # Creating DataFrame
        df = pd.DataFrame(parsed_data).T

        # Optionally, you might want to replace None with False if that's your intent
        df.fillna(value=False, inplace=True)

        df.loc["Column Total"] = df.sum()
        df["Row Total"] = df.sum(axis=1)
        df.at["Column Total", "Row Total"] = "-"

        # Displaying the DataFrame
        print(df)

        ##########
        # Average distance
        ##########

        parsed_data = {
            f"{item['name']} // {item['address']}": {
                geocoder: result["distance"]
                for geocoder, result in item["geocoding"].items()
            }
            for item in tests
        }
        df = pd.DataFrame(parsed_data).T
        df.loc["Column Average"] = df.mean()

        print(df)

    def evaluate(self, tests):
        for idx, test in enumerate(tests):
            poly_geojson = {"type": "Polygon", "coordinates": test["poly_coords"]}

            poly = GEOSGeometry(json.dumps(poly_geojson))

            for g_name, eval in test["geocoding"].items():
                if not isinstance(eval["point"], Point):
                    tests[idx]["geocoding"][g_name]["valid"] = False
                    continue

                poly.transform(2154)
                eval["point"].transform(2154)

                distance = poly.distance(eval["point"])

                if distance < 200:
                    tests[idx]["geocoding"][g_name]["distance"] = distance

                    if poly.contains(eval["point"]):
                        tests[idx]["geocoding"][g_name]["valid"] = True
                        continue

        return tests

    def geocode(self):
        tests = self.TESTS
        fns = self.get_geocoders_fns()

        for idx, test in enumerate(tests):
            ban_point = None
            if test["address"]:
                ban_point = self.geocode_ban_point(test["address"])

            tests[idx]["ban_point"] = ban_point

            tests[idx]["geocoding"] = {}

            for g_name, fn in fns.items():
                point = fn(test)

                tests[idx]["geocoding"][g_name] = {
                    "point": point,
                    "valid": None,
                    "distance": None,
                }

        return tests

    def nominatim_point(self, test) -> Optional[GEOSGeometry]:
        point = None

        nominatim = NominatimGeocoder()

        params = {"q": None, "amenity": test["name"], "countrycodes": "fr"}

        if isinstance(test["ban_point"], Point):
            vb = self.viewbox_around_point(test["ban_point"])
            params["viewbox"] = f"{vb[0]},{vb[1]},{vb[2]},{vb[3]}"

        elif isinstance(test["address"], str):
            params["q"] = test["address"]

        if isinstance(params["q"], str) or isinstance(params["amenity"], str):
            print(params)

            r = nominatim.geocode(params)

            if r["features"]:
                point = GEOSGeometry(json.dumps(r["features"][0]["geometry"]))

        return point

    def photon_point(self, test) -> Optional[GEOSGeometry]:
        point = None

        photon = PhotonGeocoder()

        params = {
            "q": test["name"],
            "lang": "fr",
        }

        if isinstance(test["ban_point"], Point):
            params["lat"] = test["ban_point"].y
            params["lon"] = test["ban_point"].x

        elif isinstance(test["address"], str):
            params["q"] = f"{test['name']} {test['address']}"

        if isinstance(params["q"], str):
            r = photon.geocode(params)

            if r["features"]:
                point = GEOSGeometry(json.dumps(r["features"][0]["geometry"]))

        return point

    def geocode_earth_point(self, test) -> Optional[GEOSGeometry]:
        point = None

        g = GeocodeEarthGeocoder()

        params = {
            "text": test["name"],
            "boundary.country": "FR",
        }

        if isinstance(test["ban_point"], Point):
            params["focus.point.lat"] = test["ban_point"].y
            params["focus.point.lon"] = test["ban_point"].x

        elif isinstance(test["address"], str):
            params["text"] = f"{test['name']} {test['address']}"

        if isinstance(params["text"], str):
            r = g.geocode(params)

            if r["features"]:
                point = GEOSGeometry(json.dumps(r["features"][0]["geometry"]))

        return point

    def geocode_ban_point(self, address) -> Optional[GEOSGeometry]:
        point = None

        g = BanGeocoder()

        r = g.geocode({"q": address})

        if r["features"]:
            point = GEOSGeometry(json.dumps(r["features"][0]["geometry"]))

        return point

    def viewbox_around_point(self, point: Point):
        new_point = point.transform(2154, clone=True)
        zone = new_point.buffer(900)
        zone.transform(4326)

        return zone.extent
