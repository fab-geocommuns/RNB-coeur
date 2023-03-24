from db import conn
from shapely.geometry import shape
from shapely.geometry.polygon import Polygon
import psycopg2
import psycopg2.extras
from jobs.import_bdnb7 import import_bdnb7
from jobs.inspect_candidates import Inspector

def sandbox():

    i = Inspector()
    i.inspect()




if __name__ == '__main__':
    sandbox()