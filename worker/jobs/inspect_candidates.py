import psycopg2
from db import get_conn
from psycopg2.extras import RealDictCursor, execute_values
from services.candidate import row_to_candidate, Candidate
from rnbid.generator import generate_rnb_id
from settings import settings


class Inspector:
    BATCH_SIZE = 50000

    def __init__(self):
        self.conn = get_conn()

        self.refusals = []
        self.creations = []
        self.updates = []

    def remove_inspected(self):
        q = "DELETE FROM batid_candidate WHERE inspected_at IS NOT NULL"
        with self.conn.cursor() as cur:
            try:
                cur.execute(q)
                self.conn.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                self.conn.rollback()
                cur.close()
                raise error

    def inspect(self) -> int:
        q, params = self.get_matches_query()

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q, params)

            c = 0
            for m_row in cur:
                c += 1
                self.inspect_match(m_row)

        # print(f"inspected: {c}")
        # print(f"refusals: {len(self.refusals)}")
        # print(f"creations: {len(self.creations)}")
        # print(f"updates: {len(self.updates)}")

        self.handle_inspected_candidates()

        return c

    def handle_inspected_candidates(self):
        self.__handle_refusals()
        self.__handle_creations()
        self.__handle_updates()

    # update all refused candidates with status 'refused'
    def __handle_refusals(self):
        print(f"refusals: {len(self.refusals)}")

        if len(self.refusals) == 0:
            return

        q = "UPDATE batid_candidate SET inspected_at = now(), inspect_result = 'refused' WHERE id in %(ids)s"

        params = {"ids": tuple([c.id for c in self.refusals])}

        with self.conn.cursor() as cur:
            try:
                cur.execute(q, params)
                self.conn.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                self.conn.rollback()
                cur.close()
                raise error

    # updated all updated candidates with status 'updated_bdg'
    def __handle_updates(self):
        print(f"updates: {len(self.updates)}")

        if len(self.updates) == 0:
            return

        q = "UPDATE batid_candidate SET inspected_at = now(), inspect_result = 'updated_bdg' WHERE id in %(ids)s"

        params = {"ids": tuple([c.id for c in self.updates])}

        with self.conn.cursor() as cur:
            try:
                cur.execute(q, params)
                self.conn.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                self.conn.rollback()
                cur.close()
                raise error

    # create new buildings for all created candidates
    def __handle_creations(self):
        print(f"creations: {len(self.creations)}")

        if len(self.creations) == 0:
            return

        # Create the buildings
        self.__create_buildings()

        # Then update the candidates
        q = "UPDATE batid_candidate SET inspected_at = now(), inspect_result = 'created_bdg' WHERE id in %(ids)s"

        params = {"ids": tuple([c.id for c in self.creations])}

        with self.conn.cursor() as cur:
            try:
                cur.execute(q, params)
                self.conn.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                self.conn.rollback()
                cur.close()
                raise error

    def __create_buildings(self):
        q = "INSERT INTO batid_building (rnb_id, source, point, shape) VALUES %s "

        values = []
        for c in self.creations:
            bdg_dict = c.to_bdg_dict()
            values.append(
                (
                    generate_rnb_id(),
                    bdg_dict["source"],
                    f"{bdg_dict['point'].wkt}",
                    f"{bdg_dict['shape'].wkt}",
                )
            )

        with self.conn.cursor() as cur:
            try:
                execute_values(cur, q, values, page_size=1000)
                self.conn.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                self.conn.rollback()
                cur.close()
                raise error

    def inspect_match(self, row):
        c = row_to_candidate(row)

        if c.is_light == True:
            self.__refuse(c)
            return

        if c.shape.area < settings["MIN_BDG_AREA"]:
            self.__refuse(c)
            return

        if row["match_cnt"] == 0:
            self.__create_new_building(c)

        if row["match_cnt"] == 1:
            self.__update_building(c)

        if row["match_cnt"] > 1:
            self.__refuse(c)

    def get_matches_query(self):
        q = (
            "SELECT c.*, count(b.id) as match_cnt "
            "from batid_candidate as c "
            "left join batid_building as b on ST_Intersects(b.shape, c.shape) "
            "and ST_Area(ST_Intersection(b.shape, c.shape)) / ST_Area(c.shape) >= %(min_intersect_ratio)s "
            "where c.inspected_at is null  "
            "group by c.id "
            "limit %(limit)s"
        )

        params = {"min_intersect_ratio": 0.85, "limit": self.BATCH_SIZE}

        return q, params

    def __update_building(self, c: Candidate):
        self.updates.append(c)

        # self.__close_inspection(c, 'updated_bdg')

    def __create_new_building(self, c: Candidate):
        self.creations.append(c)

    def __close_inspection(self, c, inspect_result):
        try:
            q = "UPDATE batid_candidate SET inspected_at = now(), inspect_result = %(inspect_result)s WHERE id = %(id)s"

            with self.conn.cursor() as cur:
                cur.execute(q, {"id": c.id, "inspect_result": inspect_result})
                self.conn.commit()
        # catch db error and rollback
        except (Exception, psycopg2.DatabaseError) as error:
            self.conn.rollback()
            self.conn.close()
            raise error

    def __refuse(self, c):
        self.refusals.append(c)

        # self.__close_inspection(c, 'refused')
