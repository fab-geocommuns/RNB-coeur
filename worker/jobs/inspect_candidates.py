import psycopg2
from db import get_conn
from psycopg2.extras import RealDictCursor
from logic.candidate import row_to_candidate, Candidate
from logic.building import generate_id
from settings import settings

class Inspector:

    BATCH_SIZE = 10000

    def inspect(self) -> int:

        q, params = self.get_matches_query()

        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q, params)

            c = 0
            for m_row in cur:
                c += 1
                print('-- inspect', c, '/', self.BATCH_SIZE)
                self.inspect_match(m_row)

            return c


    def inspect_match(self, row):

        c = row_to_candidate(row)

        if c.shape.area < settings['MIN_BDG_AREA']:
            self.__refuse(c)

        if row['match_cnt'] == 0:
            self.__create_new_building(c)

        if row['match_cnt'] == 1:
            self.__update_building(c)

        if row['match_cnt'] > 1:
            self.__refuse(c)

    def get_matches_query(self):

        q = "SELECT c.*, count(b.id) as match_cnt " \
            "from batid_candidate as c " \
            "left join batid_building as b on ST_Intersects(b.shape, c.shape) " \
            "and ST_Area(ST_Intersection(b.shape, c.shape)) / ST_Area(c.shape) >= %(min_intersect_ratio)s " \
            "where c.inspected_at is null  " \
            "group by c.id " \
            "limit %(limit)s"

        params = {
            "min_intersect_ratio": 0.85,
            "limit": self.BATCH_SIZE
        }

        return q, params

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

            conn = get_conn()
            with conn.cursor() as cur:
                try:
                    cur.execute(q, params)
                    conn.commit()
                except (Exception, psycopg2.DatabaseError) as error:
                    conn.rollback()
                    cur.close()
                    raise error


            self.__close_inspection(c, 'created_bdg')


    def __close_inspection(self, c, inspect_result):

        try:
            q = "UPDATE batid_candidate SET inspected_at = now(), inspect_result = %(inspect_result)s WHERE id = %(id)s"
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute(q, {'id': c.id, 'inspect_result': inspect_result})
                conn.commit()
        # catch db error and rollback
        except (Exception, psycopg2.DatabaseError) as error:
            conn.rollback()
            conn.close()
            raise error

    def __refuse(self, c):

        self.__close_inspection(c, 'refused')