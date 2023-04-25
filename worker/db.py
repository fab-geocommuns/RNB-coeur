import psycopg2
import os
from settings import settings
from shapely import wkb

db_name = os.environ.get("POSTGRES_NAME")
db_user = os.environ.get("POSTGRES_USER")
db_password = os.environ.get("POSTGRES_PASSWORD")
db_host = os.environ.get("POSTGRES_HOST")
db_port = os.environ.get("POSTGRES_PORT")


def get_conn():
    return psycopg2.connect(
        f"dbname='{db_name}' user='{db_user}' host='{db_host}' password='{db_password}' port='{db_port}'"
    )


def dbgeom_to_shapely(rowgeom):
    return wkb.loads(rowgeom, hex=True)


def shapely_to_dbgeom(shape):
    return wkb.dumps(shape, hex=True, srid=settings["DEFAULT_SRID"])
