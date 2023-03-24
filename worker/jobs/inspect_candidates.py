from db import conn, shapely_to_dbgeom
from psycopg2.extras import RealDictCursor
from shapely import wkb
from settings import settings
from logic.candidate import row_to_candidate, Candidate
from logic.building import generate_id


class Inspector:

    BATCH_SIZE = 10000

    def inspect(self) -> int:

        # get some candidates not inspected yet
        candidates = self.__get_candidates()

        print(f"got {len(candidates)} candidates to inspect")

        for c_row in candidates:
            c = row_to_candidate(c_row)
            self.__inspect(c)

        return len(candidates)

    def __get_candidates(self) -> list:

        q = "SELECT * from batid_candidate where inspected_at is null order by created_at limit %(limit)s"

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q, {'limit': self.BATCH_SIZE})
            return cur.fetchall()


    def __inspect(self, c: Candidate):

        if c.shape.area < settings['MIN_BDG_AREA']:
            self.__refuse(c)

        matches = self.__get_matches(c)

        if len(matches) == 0:
            self.__create_new_building(c)

        if len(matches) == 1:
            self.__update_building(c)

        if len(matches) > 1:
            self.__refuse(c)

    def __update_building(self, c: Candidate):

        self.__close_inspection(c, 'updated_bdg')

    def __create_new_building(self, c: Candidate):

            q = "INSERT INTO batid_building (rnb_id, source, point, shape) " \
                "VALUES (%(rnb_id)s, %(source)s, ST_PointOnSurface(%(shape)s), %(shape)s)"

            params = {
                "rnb_id": generate_id(),
                "shape": f"{c.shape}",
                "source": c.source
            }

            with conn.cursor() as cur:
                cur.execute(q, params)


            self.__close_inspection(c, 'created_bdg')


    def __close_inspection(self, c, inspect_result):

        try:
            q = "UPDATE batid_candidate SET inspected_at = now(), inspect_result = %(inspect_result)s WHERE id = %(id)s"
            with conn.cursor() as cur:
                cur.execute(q, {'id': c.id, 'inspect_result': inspect_result})
                conn.commit()
        # catch db error and rollback
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    def __refuse(self, c):

        self.__close_inspection(c, 'refused')

    def __get_matches(self, c: Candidate):

        q = "SELECT b.id as b_id " \
            "FROM batid_building b " \
            "WHERE ST_Intersects(b.shape, %(c_shape)s) " \
            "AND ST_Area(ST_Intersection(b.shape, %(c_shape)s)) / %(c_area)s >= %(min_intersect_ratio)s "

        params = {
            "c_shape": shapely_to_dbgeom(c.shape),
            "c_area": c.shape.area,
            "min_intersect_ratio": 0.85
        }

        with conn.cursor() as cur:
            cur.execute(q, params)
            return cur.fetchall()






