import base64
import csv
import json
import os

import psycopg2
import requests
from db import get_conn
from logic.source import Source


def import_commune_insee(state_date):
    """Imports the list of french municipalities at a given date.

    Data are retrieves using the INSEE api and are loaded to RNB database
    INSEE api related doc : https://api.insee.fr/catalogue/site/themes/wso2/subthemes/insee/pages/item-info.jag?name=M%C3%A9tadonn%C3%A9es&version=V1&provider=insee#!/geographie/getcogcomliste_1

    Args:
        state_date: date on which you wish to obtain the list of cities
    """
    src = Source("insee-cog-commune")
    src.set_param("state_date", state_date)

    # FORMER la requête

    # retrieve token
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
        "filtreNom": "Attignat",
    }

    print("-- request api insee communes data --")
    response = requests.get(src.url, params=params, headers=headers)

    # In order to perfom efficient insert in postgres db, the idea is to use copyfrom command.
    # hence, an initial write in csv is need.

    # write response to csv
    print("-- Write response to csv --")

    communes = json.loads(response.content)

    # remove unused keys and rename others
    keys_to_remove = ["type", "typeArticle"]
    keys_to_rename = {
        "code": "code_insee",
        "dateCreation": "creation_date",
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

    src.create_abs_dir()

    with open(src.path, "w") as f:
        print("-- writing buffer file --")
        cols = list(communes[0].keys())
        writer = csv.DictWriter(f, delimiter=";", fieldnames=cols)
        writer.writerows(communes)

    # Connect and populate db
    print("-- Connect and populate db --")

    conn = get_conn()

    with open(src.path, "r") as f, conn.cursor() as cursor:
        print("-- transfer buffer to db --")
        try:
            sql_query = """
            INSERT INTO batid_city (code_insee, creation_date, uri_insee, name, name_without_article)
            VALUES %s
            ON CONFLICT (code_insee) DO UPDATE
            SET creation_date = EXCLUDED.creation_date,
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
    import_commune_insee(STATE_DATE)
