from db import conn
from shapely.geometry import shape
from shapely.geometry.polygon import Polygon
import psycopg2
import psycopg2.extras
from jobs.import_bdnb7 import import_bdnb7
from jobs.import_bdtopo import import_bdtopo
from jobs.inspect_candidates import Inspector

def sandbox():

    import_bdtopo('044')






if __name__ == '__main__':
    sandbox()