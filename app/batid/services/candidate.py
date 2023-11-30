import json
import os
from dataclasses import dataclass, field
from pprint import pprint
from time import perf_counter
from typing import List, Literal
from psycopg2.extras import Json
import nanoid
import psycopg2
from django.contrib.gis.geos import MultiPolygon
from psycopg2.extras import RealDictCursor, execute_values
from shapely.geometry import MultiPolygon as ShapelyMultiPolygon
from django.db import connection, transaction
from batid.services.rnb_id import generate_rnb_id
from django.conf import settings
from batid.models import Building, BuildingStatus, BuildingImport
from batid.models import Candidate as CandidateModel
from batid.services.source import BufferToCopy
from batid.services.bdg_status import BuildingStatus as BuildingStatusService
from batid.utils.decorators import show_duration
from datetime import datetime, timezone
from collections import Counter
from django.contrib.gis.geos import GEOSGeometry


class Inspector:
    BATCH_SIZE = 10000

    MATCH_UPDATE_MIN_COVER_RATIO = 0.85
    MATCH_EXCLUDE_MAX_COVER_RATIO = 0.10

    def __init__(self):
        self.stamp = None

        self.candidates = []

        self.bdgs_to_updates = []
        self.bdg_address_relations = []

    @show_duration
    def inspect(self) -> int:
        print("\r")
        print("-- Inspect batch")

        # Adapt DB session settings for this job
        # self._adapt_db_settings()

        # Lock some candidates for this batch
        self.build_stamp()
        n = self.reserve_candidates()

        # Get candidates and inspect them
        self.get_candidates()

        print(f"all candidate : {CandidateModel.objects.all().count()}")
        print(f"candidates match: {len(self.candidates)}")

        self.inspect_candidates()

        # Now, trigger the consequences of the inspections
        self.handle_bdgs_creations()
        self.handle_bdgs_updates()
        self.handle_bdgs_refusals()

        # Clean up
        self.remove_stamped()

        return n

    def remove_stamped(self):
        print("- remove stamped candidates")
        CandidateModel.objects.filter(inspect_stamp=self.stamp).delete()

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

    def calc_bdg_update(self, c: CandidateModel, bdg: Building):
        has_changed = False
        added_address_keys = []

        # ##############################
        # PROPERTIES
        # A place to verify properties changes
        # eg: ext_rnb_id, ext_bdnb_id, ...
        # If any property has changed, we will set has_changed_props to True

        # ##
        # Prop : ext_ids
        if not bdg.contains_ext_id(c.source, c.source_version, c.source_id):
            bdg.add_ext_id(
                c.source,
                c.source_version,
                c.source_id,
                c.created_at.isoformat(),
            )
            has_changed = True

        # ##
        # Prop : shape
        if (
            self.shape_family(c.shape) == "poly"
            and self.shape_family(bdg.shape) == "point"
        ):
            bdg.shape = c.shape.clone()
            has_changed = True

        # ##############################
        # ADDRESSES
        # Handle change in address
        # We will return all the address keys that are not in the bdg

        bdg_addresses_keys = [a.id for a in bdg.addresses.all()]

        if c.address_keys:
            for c_address_key in c.address_keys:
                if c_address_key not in bdg_addresses_keys:
                    added_address_keys.append(c_address_key)
                    # for the moment we don't consider a change in address as a change in the building
                    # because we don't historize the addresses
                    # so we don't know what has changed afterwards.
                    # has_changed = True

        if has_changed:
            bdg.last_updated_by = c.created_by

        return has_changed, added_address_keys, bdg

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

    def fetch_bdg_to_updates(self):
        bdg_ids = tuple(c.matches[0]["id"] for c in self.updates)
        return (
            Building.objects.filter(id__in=bdg_ids)
            .prefetch_related("addresses")
            .only("addresses")
        )

    def update_buildings(self):
        # Get all buildings concerned by the updates
        bdgs = self.fetch_bdg_to_updates()

        # Foreach building verify if anything must be updated
        for c in self.updates:
            import_id = (
                c.created_by["id"]
                if c.created_by and c.created_by["source"] == "import"
                else None
            )

            bdg = next(b for b in bdgs if b.id == c.matches[0]["id"])
            has_changed, added_address_keys, bdg = self.calc_bdg_update(c, bdg)

            # Need to update the building properties ?
            if has_changed:
                self.bdgs_to_updates.append(bdg)

            # Need to add some building <> adresse relations ?
            if len(added_address_keys) > 0:
                self.add_addresses_to_bdg(bdg, added_address_keys)

        print(f"bdgs to update: {len(self.bdgs_to_updates)}")
        print(f"bdg address relations: {len(self.bdg_address_relations)}")

        # Save all buildings which must be updated
        self.save_bdgs_to_updates()

    def add_addresses_to_bdg(self, bdg: Building, added_address_keys: List):
        for add_key in added_address_keys:
            self.bdg_address_relations.append((bdg.rnb_id, add_key))

    @show_duration
    def save_bdgs_to_updates(self):
        # ############
        # Building properties
        # ############
        print(
            f"- save buildings properties to update ({len(self.bdgs_to_updates)} bdgs)"
        )

        if len(self.bdgs_to_updates) > 0:
            # Create a buffer file
            buffer = self.__create_update_buffer_file()

            # Count the number of occurences of each import_id
            # to update the BuildingImport entry
            import_ids = [
                bdg.last_updated_by["id"]
                for bdg in self.bdgs_to_updates
                if isinstance(bdg.last_updated_by, dict)
                and bdg.last_updated_by.get("source", None) == "import"
            ]
            import_id_stats = Counter(import_ids)

            with transaction.atomic():
                try:
                    with connection.cursor() as cur, open(buffer.path, "r") as f:
                        self.__create_tmp_update_table(cur)
                        self.__populate_tmp_update_table(buffer, cur)
                        self.__update_bdgs_from_tmp_update_table(cur)
                        self.__drop_tmp_update_table(cur)
                        os.remove(buffer.path)
                        self.bdgs_to_updates = []

                    # update the BuildingImport entry
                    for import_id, count in import_id_stats.items():
                        building_import = BuildingImport.objects.get(id=import_id)
                        building_import.building_updated_count += count
                        building_import.save()

                except (Exception, psycopg2.DatabaseError) as error:
                    raise error

        # ############
        # Building addresses relations
        # ############
        self.save_bdg_address_relations()

    def save_bdg_address_relations(self):
        print(
            f"- save buildings addresses relations to create ({len(self.bdg_address_relations)} relations)"
        )

        if len(self.bdg_address_relations) > 0:
            data = self.convert_bdg_address_relations()

            # Create a buffer file
            q = f"INSERT INTO {Building.addresses.through._meta.db_table} (building_id, address_id) VALUES %s ON CONFLICT DO NOTHING"

            with connection.cursor() as cur:
                execute_values(cur, q, data)

            self.bdg_address_relations = []

    def convert_bdg_address_relations(self) -> list:
        # The self.bdg_address_relations property is a list of tuples (rnb_id, address_id)
        # We need to convert it to a list of tuples (building_id, address_id)
        # We have to replace all rnb_id by the corresponding building_id

        # Get all rnb_id
        rnb_ids = tuple([rnb_id for rnb_id, _ in self.bdg_address_relations])
        q = f"SELECT id, rnb_id FROM {Building._meta.db_table} WHERE rnb_id in %(rnb_ids)s"
        params = {"rnb_ids": rnb_ids}

        with connection.cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()

        # Create a dict to convert rnb_id to building_id
        rnb_id_to_building_id = {rnb_id: building_id for building_id, rnb_id in rows}

        # Convert the list of tuples (rnb_id, address_id) to a list of tuples (building_id, address_id)
        data = []
        for _, (rnb_id, address_id) in enumerate(self.bdg_address_relations):
            data.append((rnb_id_to_building_id[rnb_id], address_id))

        return data

    def __update_bdgs_from_tmp_update_table(self, cursor):
        q = f"UPDATE {Building._meta.db_table} as b SET shape = tmp.shape, ext_ids = tmp.ext_ids, last_updated_by = tmp.last_updated_by FROM {self.__tmp_update_table} tmp WHERE b.id = tmp.id"
        cursor.execute(q)

    def __drop_tmp_update_table(self, cursor):
        q = f"DROP TABLE {self.__tmp_update_table}"
        cursor.execute(q)

    @property
    def __tmp_update_table(self):
        if self.stamp is None:
            raise Exception("Stamp is not set")

        return f"tmp_update_table_{self.stamp}"

    def __populate_tmp_update_table(self, buffer: BufferToCopy, cursor):
        with open(buffer.path, "r") as f:
            cursor.copy_from(
                f,
                self.__tmp_update_table,
                sep=";",
                columns=["id", "ext_ids", "shape", "last_updated_by"],
            )

    def __create_tmp_update_table(self, cursor):
        q = f"CREATE TEMPORARY TABLE {self.__tmp_update_table} (id integer, ext_ids jsonb, shape public.geometry(geometry, 4326), last_updated_by jsonb)"
        cursor.execute(q)

    def __create_update_buffer_file(self) -> BufferToCopy:
        data = []
        for bdg in self.bdgs_to_updates:
            data.append(
                {
                    "id": bdg.id,
                    "ext_ids": json.dumps(bdg.ext_ids),
                    "shape": bdg.shape.wkt,
                    "last_updated_by": json.dumps(bdg.last_updated_by),
                }
            )

        buffer = BufferToCopy()
        buffer.write_data(data)

        return buffer

    # create new buildings for all created candidates
    def handle_bdgs_creations(self):
        print(f"- creations")
        # Create the buildings
        self.create_buildings()
        self.save_bdg_address_relations()

    @property
    def creations(self):
        for c in self.candidates:
            if c.inspect_result == "creation":
                yield c

    @property
    def updates(self):
        for c in self.candidates:
            if c.inspect_result == "update":
                yield c

    @property
    def refusals(self):
        for c in self.candidates:
            if c.inspect_result == "refusal":
                yield c

    # to keep
    def handle_bdgs_updates(self):
        print(f"- updates")

        # Create the buildings
        self.update_buildings()

    def handle_bdgs_refusals(self):
        import_ids = [
            c.created_by["id"]
            for c in self.refusals
            if c.created_by["source"] == "import"
        ]
        import_id_stats = Counter(import_ids)
        with transaction.atomic():
            try:
                # update the number of refused buildings for each import
                for import_id, count in import_id_stats.items():
                    if count > 0:
                        building_import = BuildingImport.objects.get(id=import_id)
                        building_import.building_refused_count += count
                        building_import.save()
            except (Exception, psycopg2.DatabaseError) as error:
                raise error

    def candidate_to_bdg_dict(self, c: CandidateModel):
        point = c.shape if c.shape.geom_type == "Point" else c.shape.point_on_surface

        return {
            "shape": c.shape,
            "rnb_id": None,
            "source": c.source,
            "point": point,
            "address_keys": c.address_keys,
            "last_updated_by": c.created_by,
            "ext_ids": [
                {
                    "source": c.source,
                    "source_version": c.source_version,
                    "id": c.source_id,
                    "created_at": c.created_at.isoformat(),
                }
            ],
        }

    @show_duration
    def create_buildings(self):
        values = []
        # used to store the number of created buildings for each import
        import_id_stats = Counter()

        for c in self.creations:
            rnb_id = generate_rnb_id()

            bdg_dict = self.candidate_to_bdg_dict(c)

            ext_ids = bdg_dict["ext_ids"]
            ext_ids_str = json.dumps(ext_ids)
            last_updated_by = bdg_dict["last_updated_by"]

            values.append(
                (
                    rnb_id,
                    bdg_dict["source"],
                    ext_ids_str,
                    bdg_dict["point"].wkt,
                    bdg_dict["shape"].wkt,
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                    json.dumps(last_updated_by),
                )
            )

            # Add bdg <> addresses relations. They wil be created once the building are in db.
            if c.address_keys:
                for add_key in c.address_keys:
                    self.bdg_address_relations.append((rnb_id, add_key))

            if (
                type(last_updated_by) is dict
                and last_updated_by.get("source") == "import"
            ):
                import_id_stats.update([last_updated_by["id"]])

        # Anything to save?
        if len(values) == 0:
            # No? Then quit
            return

        buffer = BufferToCopy()
        buffer.write_data(values)

        with transaction.atomic():
            try:
                start = perf_counter()
                with connection.cursor() as cursor, open(buffer.path, "r") as f:
                    cursor.copy_from(
                        f,
                        Building._meta.db_table,
                        sep=";",
                        columns=(
                            "rnb_id",
                            "source",
                            "ext_ids",
                            "point",
                            "shape",
                            "created_at",
                            "updated_at",
                            "last_updated_by",
                        ),
                    )
                end = perf_counter()
                os.remove(buffer.path)
                print(f"---- create_buildings : copy_from: {end - start:.2f}s")

                # update the number of created buildings for each import
                for import_id, count in import_id_stats.items():
                    building_import = BuildingImport.objects.get(id=import_id)
                    building_import.building_created_count += count
                    building_import.save()

            except (Exception, psycopg2.DatabaseError) as error:
                raise error

    def compute_shape_area(self, shape):
        with connection.cursor() as cursor:
            cursor.execute("select ST_AREA(%s, true)", [shape.wkt])
            row = cursor.fetchone()

        return row[0]

    def inspect_candidate(self, c: CandidateModel):
        print("---")
        print(f"candidate {c.id}")
        print(f"matches: {len(c.matches)}")

        # Light buildings do not match the RNB building definition
        if c.is_light == True:
            self.set_inspect_result(c, "refusal")
            return

        if (
            self.shape_family(c.shape) == "poly"
            and self.compute_shape_area(c.shape) < settings.MIN_BDG_AREA
        ):
            self.set_inspect_result(c, "refusal")
            return

        # We inspect the matches
        self.inspect_candidate_matches(c)

    def inspect_candidate_matches(self, c: CandidateModel):
        kept_matches = []
        c_area = self.compute_shape_area(c.shape)

        for match in c.matches:
            b_shape = GEOSGeometry(json.dumps(match["shape"]))

            shape_match_result = self.match_shapes(c.shape, b_shape)

            if shape_match_result == "match":
                kept_matches.append(match)
                continue

            if shape_match_result == "no_match":
                continue

            if shape_match_result == "conflict":
                self.set_inspect_result(c, "refusal")
                return

        # We transfer the kept matches ids to the candidate
        # We do not keep buildings shapes in memory to avoid memory issues
        c.matches = kept_matches

        if len(c.matches) == 0:
            self.set_inspect_result(c, "creation")

        if len(c.matches) == 1:
            self.set_inspect_result(c, "update")

        if len(c.matches) > 1:
            self.set_inspect_result(c, "refusal")

    def match_shapes(
        self, a: GEOSGeometry, b: GEOSGeometry
    ) -> Literal["match", "no_match", "conflict"]:
        families = (self.shape_family(a), self.shape_family(b))

        if families == ("poly", "poly"):
            return self.match_polygons(a, b)

        if families == ("point", "point"):
            return self.match_points(a, b)

        if families == ("point", "poly") or families == ("poly", "point"):
            return self.match_point_poly(a, b)

        raise Exception(f"Unknown matching shape families case: {families}")

    def match_polygons(
        self, a: GEOSGeometry, b: GEOSGeometry
    ) -> Literal["match", "no_match", "conflict"]:
        a_area = self.compute_shape_area(a)
        b_area = self.compute_shape_area(b)

        intersection = a.intersection(b)
        intersection_area = self.compute_shape_area(intersection)

        a_cover_ratio = intersection_area / a_area
        b_cover_ratio = intersection_area / b_area

        # The building does not intersect enough with the candidate to be considered as a match
        if (
            a_cover_ratio < self.MATCH_EXCLUDE_MAX_COVER_RATIO
            and b_cover_ratio < self.MATCH_EXCLUDE_MAX_COVER_RATIO
        ):
            return "no_match"

        # The building intersects significantly with the candidate but not enough to be considered as a match
        if (
            a_cover_ratio < self.MATCH_UPDATE_MIN_COVER_RATIO
            or b_cover_ratio < self.MATCH_UPDATE_MIN_COVER_RATIO
        ):
            return "conflict"

        return "match"

    def match_points(
        self, a: GEOSGeometry, b: GEOSGeometry
    ) -> Literal["match", "no_match", "conflict"]:
        # NB : this intersection verification is already done in the sql query BUT we want to be sure this matching condition is always verified even the SQL query is modified
        if a.intersects(b):
            return "match"

        return "no_match"

    def match_point_poly(
        self, a: GEOSGeometry, b: GEOSGeometry
    ) -> Literal["match", "no_match", "conflict"]:
        # NB : this intersection verification is already done in the sql query BUT we want to be sure this matching condition is always verified even the SQL query is modified
        if a.intersects(b):
            return "match"

        return "no_match"

    @staticmethod
    def shape_family(shape: GEOSGeometry):
        if shape.geom_type == "MultiPolygon":
            return "poly"

        if shape.geom_type == "Polygon":
            return "poly"

        if shape.geom_type == "Point":
            return "point"

        raise Exception(
            f"We do not handle this shape type: {shape.geom_type} in inspector"
        )

    def set_inspect_result(self, c: CandidateModel, result: str):
        c.inspect_result = result
        c.inspected_at = datetime.now(timezone.utc)

    @show_duration
    def inspect_candidates(self):
        for c in self.candidates:
            self.inspect_candidate(c)

    @show_duration
    def get_candidates(self):
        print(f"- get_candidates")
        params = {
            "status": tuple(BuildingStatusService.REAL_BUILDINGS_STATUS),
            "limit": self.BATCH_SIZE,
            "inspect_stamp": self.stamp,
        }

        q = (
            "SELECT c.id, ST_AsEWKB(c.shape) as shape, COALESCE(json_agg(json_build_object('id', b.id, 'shape', b.shape)) FILTER (WHERE b.id IS NOT NULL), '[]') as matches "
            f"FROM {CandidateModel._meta.db_table} c "
            f"LEFT JOIN {Building._meta.db_table} b on ST_Intersects(c.shape, b.shape) "
            f"LEFT JOIN {BuildingStatus._meta.db_table} bs on bs.building_id = b.id "
            "WHERE ((bs.type IN %(status)s AND bs.is_current) OR bs.id IS NULL) "
            "AND c.inspected_at IS NULL AND c.inspect_stamp = %(inspect_stamp)s "
            "GROUP BY c.id "
            "LIMIT %(limit)s"
        )

        self.candidates = CandidateModel.objects.raw(q, params)

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

        # self.__close_inspection(c, 'refused')

    def _adapt_db_settings(self):
        with connection.cursor() as cur:
            cur.execute("SET work_mem TO '200MB';")
            cur.execute("SET maintenance_work_mem TO '1GB';")
            cur.execute("SET max_parallel_workers_per_gather TO 4;")
            connection.commit()

        pass

    def build_stamp(self):
        # The stamp must be lowercase since pg seems to lowercase it anyway
        # Postegresql uses the stamp to create a temporary table
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        self.stamp = nanoid.generate(size=12, alphabet=alphabet).lower()
        print(f"- stamp : {self.stamp}")

    def reserve_candidates(self):
        print("- reserve candidates")
        with transaction.atomic():
            # select_for_update() will lock the selected rows until the end of the transaction
            # avoid that another inspector selects the same candidates between the select and the update of this one
            candidates = (
                CandidateModel.objects.select_for_update()
                .filter(inspect_stamp__isnull=True)
                .order_by("id")[: self.BATCH_SIZE]
            )

            return CandidateModel.objects.filter(id__in=candidates).update(
                inspect_stamp=self.stamp
            )
