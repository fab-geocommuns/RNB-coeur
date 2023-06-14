import base64
import csv
import json
import os

import psycopg2
import requests
from django.db import connection
from batid.services.source import Source
from batid.services.city import fetch_dpt_cities_geojson
from batid.models import City
from psycopg2.extras import execute_values

# from settings import settings
from django.conf import settings

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon


def import_etalab_cities(dpt: str):
    cities_geojson = fetch_dpt_cities_geojson(dpt)

    for c in cities_geojson["features"]:
        geom = GEOSGeometry(json.dumps(c["geometry"]), srid=4326)

        if geom.geom_type == "Polygon":
            # transform into a multipolygon
            geom = MultiPolygon([geom], srid=4326)

        geom.transform(settings.DEFAULT_SRID)

        try:
            city = City.objects.get(code_insee=c["properties"]["code"])
        except City.DoesNotExist:
            city = City(code_insee=c["properties"]["code"])

        city.shape = geom
        city.name = c["properties"]["nom"]
        city.save()

    # q = (
    #     f"INSERT INTO {City._meta.db_table} (code_insee, name, shape) VALUES (%(code_insee)s, %(name)s, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(shape)s), 4326), %(db_srid)s)) "
    #     "ON CONFLICT (code_insee) DO UPDATE "
    #     "SET code_insee = EXCLUDED.code_insee, name = EXCLUDED.name, shape = EXCLUDED.shape"
    # )
    #
    # with connection.cursor() as cursor:
    #     for c in cities_geojson["features"]:
    #         print(f'--- {c["properties"]["nom"]} ---')
    #
    #         shape = c["geometry"]
    #         if shape["type"] == "Polygon":
    #             shape["coordinates"] = [shape["coordinates"]]
    #             shape["type"] = "MultiPolygon"
    #
    #         params = {
    #             "code_insee": c["properties"]["code"],
    #             "name": c["properties"]["nom"],
    #             "shape": json.dumps(shape),
    #             "db_srid": settings.DEFAULT_SRID,
    #         }
    #
    #         try:
    #             cursor.execute(q, params)
    #             # connection.commit()
    #         except (Exception, psycopg2.DatabaseError) as error:
    #             connection.rollback()
    #             cursor.close()
    #             raise error


def import_insee_cities(state_date):
    """Imports the list of french municipalities at a given date.

    Data are retrieves using the INSEE api and are loaded to RNB database
    INSEE api related doc : https://api.insee.fr/catalogue/site/themes/wso2/subthemes/insee/pages/item-info.jag?name=M%C3%A9tadonn%C3%A9es&version=V1&provider=insee#!/geographie/getcogcomliste_1

    Args:
        state_date: date on which you wish to obtain the list of cities
    """
    src = Source("insee-cog-commune")
    src.set_param("state_date", state_date)

    # Retrieve token
    token = retrieve_token(
        consumer_key=os.environ.get("INSEE_CONSUMER_KEY"),
        consumer_secret=os.environ.get("INSEE_CONSUMER_SECRET"),
    )

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

    params = {
        "date": state_date,
        "com": "true",  # to inclue Outre-Mer cities
    }

    print("-- request api insee communes data --")
    response = requests.get(src.url, params=params, headers=headers)

    communes = json.loads(response.content)

    # remove unused keys and rename others
    keys_to_remove = ["type", "typeArticle", "uri", "intituleSansArticle"]
    keys_to_rename = {
        "code": "code_insee",
        "dateCreation": "established_at",
        "intitule": "name",
    }

    for i, commune in enumerate(communes):
        print("------")
        print(commune)

        for key in keys_to_remove:
            commune.pop(key, None)

        for key in list(commune):
            if key in keys_to_rename:
                commune[keys_to_rename[key]] = commune.pop(key)

        communes[i] = commune

    communes_tuples = [
        (
            c["code_insee"],
            c["established_at"],
            c["name"],
        )
        for c in communes
    ]

    # Connect and populate db
    print("-- Connect and populate db --")

    with connection.cursor() as cursor:
        print("-- transfer cities to db --")
        try:
            sql_query = """
            INSERT INTO batid_city (code_insee, established_at, name)
            VALUES %s
            ON CONFLICT (code_insee) DO UPDATE
            SET created_at = EXCLUDED.created_at,
                uri_insee = EXCLUDED.uri_insee,
                name = EXCLUDED.name,
                name_without_article = EXCLUDED.name_without_article ;
            """

            # Execute the query with the list of tuples
            execute_values(cursor, sql_query, communes_tuples)

            connection.commit()
        except (Exception, psycopg2.DatabaseError) as error:
            connection.rollback()
            cursor.close()
            raise error

            print("- remove buffer")
            os.remove(src.path)


def retrieve_token(consumer_key: str, consumer_secret: str) -> str:
    """Retrieves Token based on client secrets"""
    encodedData = base64.b64encode(
        bytes(f"{consumer_key}:{consumer_secret}", "ISO-8859-1")
    ).decode("ascii")

    headers = {
        "Authorization": f"Basic {encodedData}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {"grant_type": "client_credentials"}
    url = os.environ.get("INSEE_TOKEN_URL")
    response = requests.post(url, headers=headers, data=data, verify=False)

    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise ValueError(response.status_code, response.text)
