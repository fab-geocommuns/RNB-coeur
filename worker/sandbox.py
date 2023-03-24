from db import conn
from shapely.geometry import shape
from shapely.geometry.polygon import Polygon
import psycopg2
import psycopg2.extras
from jobs.import_bdnb7 import import_bdnb7

def sandbox():

    import_bdnb7("31")




if __name__ == '__main__':
    sandbox()