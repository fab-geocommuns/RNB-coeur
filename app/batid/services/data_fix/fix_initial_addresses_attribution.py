import time
from datetime import datetime
from typing import Union

from django.db import connection

from batid.models import Building
from batid.models import BuildingHistoryOnly
from batid.models import BuildingImport

Numeric = Union[int, float]


def impacted_buildings_query(
    correct_addresses_historisation_date: datetime,
    from_rnb_id: str,
    to_rnb_id: str,
    limit: int,
) -> str:
    return f"""
with
impacted_bdnb_import_ids as (
select
	id
from
	batid_buildingimport as bi
where
	bi.import_source ilike 'bdnb%'
	and bi.created_at < '{correct_addresses_historisation_date.isoformat()}'
),
all_bdtopo_import_ids as (
select
	id
from
	batid_buildingimport as bi
where
	bi.import_source ilike 'bdtopo%'
),
potential_bdnb_history_items as (
select
	*
from
	batid_building_history
where
	event_origin->>'source' = 'import'
	and event_origin->>'id' in (
	select
		id ::text
	from
		impacted_bdnb_import_ids)
	and (addresses_id is null
		or cardinality(addresses_id) = 0)
),
bdtopo_hitems_with_addresses as (
select
	*
from
	batid_building_with_history
where
	event_origin->>'source' = 'import'
	and event_origin->>'id' in (
	select
		id ::text
	from
		all_bdtopo_import_ids)
	and cardinality(addresses_id) > 0
),
problematic_bdnb_items as (
select
	bdnb_hi.*,
	bdtopo_hi.bh_id as bdtopo_bh_id
from
	potential_bdnb_history_items as bdnb_hi
join bdtopo_hitems_with_addresses as bdtopo_hi
on
	bdnb_hi.rnb_id = bdtopo_hi.rnb_id
	and lower(bdtopo_hi.sys_period) = upper(bdnb_hi.sys_period)
)
select
	bdtopo_bh_id, rnb_id
from
	problematic_bdnb_items
where rnb_id > '{from_rnb_id}' and rnb_id <= '{to_rnb_id}'
limit {limit};
    """


class InitialAddressesAttributionDataFix:
    def __init__(
        self,
        correct_addresses_historisation_date: datetime = datetime(2024, 5, 1),
        from_rnb_id: str = "0",
        to_rnb_id: str = "ZZZZZZZZZZZZ",
        batch_size: int = 10000,
    ):
        self.correct_addresses_historisation_date = correct_addresses_historisation_date
        self.from_rnb_id = from_rnb_id
        self.to_rnb_id = to_rnb_id
        self.batch_size = batch_size

    def fix_all(self):
        while True:
            time_start = time.time()
            bdtopo_history_item_ids = self._query_impacted_bdtopo_history_item_ids(
                limit=self.batch_size
            )
            if len(bdtopo_history_item_ids) == 0:
                break
            for bdtopo_history_item_id, rnb_id in bdtopo_history_item_ids:
                self.fix_building_with_history(bdtopo_history_item_id, rnb_id)
            time_end = time.time()
            print(f"Time taken: {time_end - time_start} seconds", flush=True)

    def _query_impacted_bdtopo_history_item_ids(
        self, limit: int
    ) -> list[tuple[int, str]]:
        with connection.cursor() as cursor:
            raw_sql = impacted_buildings_query(
                self.correct_addresses_historisation_date,
                self.from_rnb_id,
                self.to_rnb_id,
                limit,
            )
            cursor.execute(raw_sql)
            return [(row[0], row[1]) for row in cursor.fetchall()]

    def fix_building_with_history(
        self, bdtopo_history_item_id: int | None, rnb_id: str
    ):
        previous_item_sys_period_start = None
        addresses_id = None
        if bdtopo_history_item_id is None:
            building = Building.objects.get(rnb_id=rnb_id)
            addresses_id = building.addresses_id
            previous_item_sys_period_start = building.sys_period.lower
        else:
            building_history_item = BuildingHistoryOnly.objects.get(
                bh_id=bdtopo_history_item_id
            )
            addresses_id = building_history_item.addresses_id
            previous_item_sys_period_start = building_history_item.sys_period.lower

        if addresses_id is None:
            raise Exception(
                f"Building {rnb_id} has no addresses_id on its history item"
            )

        while True:
            previous_history_item = BuildingHistoryOnly.objects.filter(
                rnb_id=rnb_id,
                sys_period__endswith=previous_item_sys_period_start,
            ).first()
            if previous_history_item is None:
                break
            previous_item_sys_period_start = previous_history_item.sys_period.lower
            previous_item_bh_id = previous_history_item.bh_id
            if previous_history_item.addresses_id is not None:
                raise Exception(
                    f"Previous history item {previous_history_item.id} has addresses_id"
                )
            if previous_history_item.event_origin["source"] != "import":
                raise Exception(
                    f"Previous history item {previous_history_item.id} is not an import"
                )
            origin_import_id = previous_history_item.event_origin["id"]
            if origin_import_id not in self._impacted_bdnb_import_ids():
                raise Exception(
                    f"Previous history item {previous_history_item.id} is not an impacted import"
                )
            sql = "UPDATE batid_building_history SET addresses_id = %s WHERE bh_id = %s"
            with connection.cursor() as cursor:
                # print(sql, addresses_id, previous_item_bh_id)

                cursor.execute(
                    sql,
                    (addresses_id, previous_item_bh_id),
                )

    def _impacted_bdnb_import_ids(self) -> list[int]:
        if not hasattr(self, "__impacted_bdnb_import_ids"):
            self.__impacted_bdnb_import_ids = BuildingImport.objects.filter(
                import_source__icontains="bdnb",
                created_at__lt=self.correct_addresses_historisation_date,
            ).values_list("id", flat=True)
        return self.__impacted_bdnb_import_ids
