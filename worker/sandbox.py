from db import conn
from shapely.geometry import shape
from shapely.geometry.polygon import Polygon
import psycopg2
import psycopg2.extras

def sandbox():

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:

        pdict = {
        "coordinates": [
          [
            [
              5.714546138971144,
              45.183582017967495
            ],
            [
              5.714307722736351,
              45.18327743612505
            ],
            [
              5.714307722736351,
              45.182902833234124
            ],
            [
              5.714923631343964,
              45.18282931275078
            ],
            [
              5.715097476515012,
              45.18354700864316
            ],
            [
              5.714546138971144,
              45.183582017967495
            ]
          ]
        ],
        "type": "Polygon"
      }
        poly = shape(pdict)
        params = {
            'poly': f"{poly}"
        }

        cursor.execute('SELECT * '
                       'FROM batid_building as b '
                       'WHERE ST_Intersects(b.shape, ST_Transform(ST_GeomFromText(%(poly)s, 4326), 2154)) '
                       'LIMIT 100', params)

        for row in cursor.fetchall():
            print(row['rnb_id'])



    pass



if __name__ == '__main__':
    sandbox()