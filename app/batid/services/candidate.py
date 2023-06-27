import os
from dataclasses import dataclass, field
from time import perf_counter
from typing import List

import psycopg2
from django.contrib.gis.geos import MultiPolygon
from psycopg2.extras import RealDictCursor, execute_values
from shapely.geometry import MultiPolygon as ShapelyMultiPolygon
from django.db import connection
from batid.services.geo import dbgeom_to_shapely
from batid.services.rnb_id import generate_rnb_id
from django.conf import settings
from batid.models import Building
from batid.models import Candidate as CandidateModel
from batid.services.source import BufferToCopy
from batid.utils.db import dictfetchall
from datetime import datetime, timezone


# todo : convert old worker approach (dataclass to mimic django model) to new approach (django model)
@dataclass
class Candidate:
    id: int
    shape: ShapelyMultiPolygon
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
        self.zone = None  # MultiPolygon

        self.refusals = []
        self.creations = []
        self.updates = []

    def remove_inspected(self):
        q = f"DELETE FROM {CandidateModel._meta.db_table} WHERE inspected_at IS NOT NULL"
        with connection.cursor() as cur:
            try:
                cur.execute(q)
                connection.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                connection.rollback()
                cur.close()
                raise error

        self.clean_candidate_table()

    def remove_invalid_candidates(self):
        q = (
            f"DELETE FROM {CandidateModel._meta.db_table} WHERE shape IS NULL "
            "OR ST_IsEmpty(shape) "
            "OR ST_IsValid(shape) = false "
            "OR ST_Area(shape) = 0 "
        )
        with connection.cursor() as cur:
            try:
                cur.execute(q)
                connection.commit()
            except (Exception, psycopg2.DatabaseError) as error:
                connection.rollback()
                cur.close()
                raise error

        self.clean_candidate_table()

    def inspect(self) -> int:
        print("\r")
        print("-- Inspect batch")

        self._adapt_db_settings()

        b_start = perf_counter()
        q, params = self.get_matches_query()

        with connection.cursor() as cur:
            start = perf_counter()
            matches = dictfetchall(cur, q, params)
            end = perf_counter()
            print(f"fetch_matches: {end - start:.2f}s")

            c = 0
            start = perf_counter()
            for m_row in matches:
                c += 1
                self.inspect_match(m_row)
            end = perf_counter()
            print(f"inspect_match: {end - start:.2f}s")

        self.handle_inspected_candidates()

        start = perf_counter()
        self.clean_candidate_table()
        self.clean_bdg_table()
        end = perf_counter()
        print(f"clean db tables: {end - start:.2f}s")

        b_end = perf_counter()

        print(f"Total batch time: {b_end - b_start:.2f}s")

        return c

    def handle_inspected_candidates(self):
        start = perf_counter()
        self.__handle_refusals()
        end = perf_counter()
        print(f"handle_refusals: {end - start:.2f}s")

        start = perf_counter()
        self.__handle_creations()
        end = perf_counter()
        print(f"handle_creations: {end - start:.2f}s")

        start = perf_counter()
        self.__handle_updates()
        end = perf_counter()
        print(f"handle_updates: {end - start:.2f}s")

    # update all refused candidates with status 'refused'
    def __handle_refusals(self):
        print(f"refusals: {len(self.refusals)}")

        if len(self.refusals) == 0:
            return

        ids = tuple([c.id for c in self.refusals])
        self.__remove_candidates(ids)

    def __remove_candidates(self, ids: tuple):
        q = f"DELETE FROM {CandidateModel._meta.db_table} WHERE id in %(ids)s"
        params = {"ids": ids}

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

        ids = tuple([c.id for c in self.updates])
        self.__remove_candidates(ids)

    # create new buildings for all created candidates
    def __handle_creations(self):
        print(f"creations: {len(self.creations)}")

        if len(self.creations) == 0:
            return

        # Create the buildings
        start = perf_counter()
        self.__create_buildings()
        end = perf_counter()
        print(f"-- create_buildings: {end - start:.2f}s")

        # Remove handled candidates
        ids = tuple([c.id for c in self.creations])
        self.__remove_candidates(ids)

    def __create_buildings(self):
        buffer = BufferToCopy()

        q = f"INSERT INTO {Building._meta.db_table} (rnb_id, source, point, shape, created_at, updated_at) VALUES %s "

        values = []

        start = perf_counter()
        for c in self.creations:
            bdg_dict = c.to_bdg_dict()
            values.append(
                (
                    generate_rnb_id(),
                    bdg_dict["source"],
                    f"{bdg_dict['point'].wkt}",
                    f"{bdg_dict['shape'].wkt}",
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                )
            )

        buffer.write_data(values)
        end = perf_counter()
        print(f"---- create_buildings : calculate values: {end - start:.2f}s")

        with connection.cursor() as cur, open(buffer.path, "r") as f:
            try:
                start = perf_counter()
                cur.copy_from(
                    f,
                    Building._meta.db_table,
                    sep=";",
                    columns=(
                        "rnb_id",
                        "source",
                        "point",
                        "shape",
                        "created_at",
                        "updated_at",
                    ),
                )
                end = perf_counter()
                os.remove(buffer.path)
                print(f"---- create_buildings : execute_values: {end - start:.2f}s")
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
        params = {"min_intersect_ratio": 0.85, "limit": self.BATCH_SIZE}

        where_conds = ["c.inspected_at is null"]

        if isinstance(self.zone, MultiPolygon):
            where_conds.append("ST_Intersects(c.shape, %(zone)s)")
            params["zone"] = f"{self.zone}"

        q = (
            "SELECT c.*, count(b.id) as match_cnt "
            f"from {CandidateModel._meta.db_table} as c "
            "left join batid_building as b on ST_Intersects(b.shape, c.shape) "
            "and ST_Area(ST_Intersection(b.shape, c.shape)) / ST_Area(c.shape) >= %(min_intersect_ratio)s "
            f"where {' and '.join(where_conds)}  "
            "group by c.id "
            "limit %(limit)s"
        )

        return q, params

    def __update_building(self, c: Candidate):
        self.updates.append(c)

        # self.__close_inspection(c, 'updated_bdg')

    def __create_new_building(self, c: Candidate):
        self.creations.append(c)

    def __close_inspection(self, c, inspect_result):
        try:
            q = f"UPDATE {CandidateModel._meta.db_table} SET inspected_at = now(), inspect_result = %(inspect_result)s WHERE id = %(id)s"

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

    def _adapt_db_settings(self):
        with connection.cursor() as cur:
            cur.execute("SET work_mem TO '200MB';")
            connection.commit()

            cur.execute("SET maintenance_work_mem TO '1GB';")
            connection.commit()

            cur.execute("SET max_parallel_workers_per_gather TO 4;")
            connection.commit()

        pass

    def clean_candidate_table(self):
        # print("clean_candidate_table")
        # q = f"VACUUM ANALYZE {CandidateModel._meta.db_table};"
        # with connection.cursor() as cur:
        #     cur.execute(q)
        #     connection.commit()

        pass

    def clean_bdg_table(self):
        # print("clean_bdg_table")
        # q = f"VACUUM ANALYZE {Building._meta.db_table};"
        # with connection.cursor() as cur:
        #     cur.execute(q)
        #     connection.commit()

        pass
