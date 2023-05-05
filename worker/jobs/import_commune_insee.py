import base64
import csv
import json
import os

import psycopg2
import requests
from db import get_conn
from logic.source import Source
from psycopg2.extras import execute_values


def import_commune_insee(state_date):
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
    keys_to_remove = ["type", "typeArticle"]
    keys_to_rename = {
        "code": "code_insee",
        "dateCreation": "created_at",
        "uri": "uri_insee",
        "intitule": "name",
        "intituleSansArticle": "name_without_article",
    }

    for i, commune in enumerate(communes):
        for key in keys_to_remove:
            commune.pop(key, None)

        for key in list(commune):
            if key in keys_to_rename:
                commune[keys_to_rename[key]] = commune.pop(key)

        communes[i] = commune

    communes_tuples = [
        (
            c["code_insee"],
            c["created_at"],
            c["uri_insee"],
            c["name"],
            c["name_without_article"],
        )
        for c in communes
    ]

    # Connect and populate db
    print("-- Connect and populate db --")

    conn = get_conn()

    with conn.cursor() as cursor:
        print("-- transfer cities to db --")
        try:
            sql_query = """
            INSERT INTO batid_city (code_insee, created_at, uri_insee, name, name_without_article)
            VALUES %s
            ON CONFLICT (code_insee) DO UPDATE
            SET created_at = EXCLUDED.created_at,
                uri_insee = EXCLUDED.uri_insee,
                name = EXCLUDED.name,
                name_without_article = EXCLUDED.name_without_article ;
            """

            # Execute the query with the list of tuples
            execute_values(cursor, sql_query, communes_tuples)

            conn.commit()
        except (Exception, psycopg2.DatabaseError) as error:
            conn.rollback()
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


if __name__ == "__main__":
    STATE_DATE = os.environ.get("INSEE_STATE_DATE")
    import_commune_insee(STATE_DATE)
