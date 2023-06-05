from dataclasses import dataclass, field
from typing import List

import psycopg2
from psycopg2.extras import RealDictCursor
from shapely.geometry import MultiPolygon
from django.db import connection
from datetime import datetime
from batid.services.geo import dbgeom_to_shapely
from batid.services.rnb_id import generate_rnb_id
from django.conf import settings
from batid.models import Building, Candidate


@dataclass
class Candidate:
    id: int
    shape: MultiPolygon
    is_light: bool
    source: str
    source_id: str
    address_keys: List[str]
    created_at: datetime
    inspected_at: datetime
    inspect_result: str

    def to_bdg_dict(self):
        return {
            "shape": self.shape,
            "rnb_id": None,
            "source": self.source,
            "point": self.shape.point_on_surface(),
        }


def row_to_candidate(row):
    return Candidate(
        id=row["id"],
        shape=dbgeom_to_shapely(row.get("shape", None)),
        source=row["source"],
        is_light=row["is_light"],
        source_id=row["source_id"],
        address_keys=row["address_keys"],
        created_at=row.get("created_at", None),
        inspected_at=row.get("inspected_at", None),
        inspect_result=row.get("inspect_result", None),
    )


class Inspector:
    BATCH_SIZE = 50000

    def __init__(self):
        self.refusals = []
        self.creations = []
        self.updates = []

    def remove_inspected(self):
        q = f"DELETE FROM {Candidate._meta.db_table} WHERE inspected_at IS NOT NULL"
        with connection.cursor() as cur:
            try:
                cur.execute(q)
                connection.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                connection.rollback()
                cur.close()
                raise error

    def inspect(self) -> int:
        q, params = self.get_matches_query()

        with connection.cursor(cursor_factory=RealDictCursor) as cur:
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

        with connection.cursor() as cur:
            try:
                cur.execute(q, params)
                connection.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                connection.rollback()
                cur.close()
                raise error

    # updated all updated candidates with status 'updated_bdg'
    def __handle_updates(self):
        print(f"updates: {len(self.updates)}")

        if len(self.updates) == 0:
            return

        q = "UPDATE batid_candidate SET inspected_at = now(), inspect_result = 'updated_bdg' WHERE id in %(ids)s"

        params = {"ids": tuple([c.id for c in self.updates])}

        with connection.cursor() as cur:
            try:
                cur.execute(q, params)
                connection.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                connection.rollback()
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

        with connection.cursor() as cur:
            try:
                cur.execute(q, params)
                connection.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                connection.rollback()
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

        with connection.cursor() as cur:
            try:
                execute_values(cur, q, values, page_size=1000)
                connection.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                connection.rollback()
                cur.close()
                raise error

    def inspect_match(self, row):
        c = row_to_candidate(row)

        if c.is_light == True:
            self.__refuse(c)
            return

        if c.shape.area < settings.MIN_BDG_AREA:
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
            f"from {Candidate._meta.db_table} as c "
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

            with connection.cursor() as cur:
                cur.execute(q, {"id": c.id, "inspect_result": inspect_result})
                connection.commit()
        # catch db error and rollback
        except (Exception, psycopg2.DatabaseError) as error:
            connection.rollback()
            connection.close()
            raise error

    def __refuse(self, c):
        self.refusals.append(c)

        # self.__close_inspection(c, 'refused')
