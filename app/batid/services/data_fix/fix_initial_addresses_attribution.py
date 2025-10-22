from django.db import transaction, connection
from batid.models import BuildingHistoryOnly, BuildingWithHistory, BuildingImport
from typing import TypedDict
from datetime import datetime
from typing import Iterable


class BuildingHistoryItemPair(TypedDict):
    rnb_id: str
    bdtopo_history_or_building_item: BuildingWithHistory
    bdnb_history_item: BuildingHistoryOnly


class InitialAddressesAttributionDataFix:
    def __init__(self, batch_size: int = 10000, start_id: int = 0) -> None:
        self.batch_size = batch_size
        self.start_id = start_id
        self.correct_addresses_historisation_date = datetime(2024, 5, 1)

    def fix_all(self) -> None:
        current_id = self.start_id
        affected_bdnb_import_ids = self._get_affected_bdnb_import_ids()
        affected_bdtopo_import_ids = self._get_affected_bdtopo_import_ids()
        while True:
            updated_row_count = self.fix_batch_initial_addresses_attribution(
                current_id, affected_bdnb_import_ids, affected_bdtopo_import_ids
            )
            if updated_row_count == 0:
                break
            current_id += updated_row_count
            print(f"Updated {updated_row_count} rows")

    def fix_batch_initial_addresses_attribution(
        self,
        current_id: int,
        affected_bdnb_import_ids: list[int],
        affected_bdtopo_import_ids: list[int],
    ) -> int:
        updated_row_count = 0

        with transaction.atomic():
            building_history_item_pairs = self._get_building_history_item_pairs_with_missing_initial_address_attribution(
                current_id, affected_bdnb_import_ids, affected_bdtopo_import_ids
            )
            for building_history_item_pair in building_history_item_pairs:
                if self._should_fix_single_initial_addresses_attribution(
                    building_history_item_pair
                ):
                    self._fix_single_initial_addresses_attribution(
                        building_history_item_pair
                    )
                    updated_row_count += 1
        return updated_row_count

    def _get_affected_bdnb_import_ids(self) -> list[int]:
        return BuildingImport.objects.filter(
            import_source__startswith="bdnb_",
            created_at__lt=self.correct_addresses_historisation_date,
        ).values_list("id", flat=True)

    def _get_affected_bdtopo_import_ids(self) -> list[int]:
        return BuildingImport.objects.filter(
            import_source__startswith="bdtopo_",
            created_at__lt=self.correct_addresses_historisation_date,
        ).values_list("id", flat=True)

    def _should_fix_single_initial_addresses_attribution(
        self,
        building_history_item_pair: BuildingHistoryItemPair,
    ) -> bool:
        bdtopo_history_or_building_item = building_history_item_pair[
            "bdtopo_history_or_building_item"
        ]
        bdnb_history_item = building_history_item_pair["bdnb_history_item"]
        return (
            bdnb_history_item.addresses_id is None
            and bdtopo_history_or_building_item.addresses_id is not None
            and bdtopo_history_or_building_item.addresses_id != []
        )

    def _fix_single_initial_addresses_attribution(
        self,
        building_history_item_pair: BuildingHistoryItemPair,
    ) -> None:
        bdtopo_history_or_building_item = building_history_item_pair[
            "bdtopo_history_or_building_item"
        ]
        bdnb_history_item = building_history_item_pair["bdnb_history_item"]
        with connection.cursor() as cursor:
            sql = "UPDATE batid_buildinghistoryonly SET addresses_id = %s WHERE bh_id = %s"
            args = (
                bdtopo_history_or_building_item.addresses_id,
                bdnb_history_item.bh_id,
            )
            print(sql % args)
            cursor.execute(
                sql,
                args,
            )

    def _get_building_history_item_pairs_with_missing_initial_address_attribution(
        self,
        current_id: int,
        affected_bdnb_import_ids: list[int],
        affected_bdtopo_import_ids: list[int],
    ) -> list[BuildingHistoryItemPair]:
        result: list[BuildingHistoryItemPair] = []

        candidate_bdnb_history_items = BuildingHistoryOnly.objects.filter(
            event_origin__source="import",
            event_origin__id__in=affected_bdnb_import_ids,
            bh_id__gt=current_id,
            addresses_id__isnull=True,
        )

        bdtopo_history_or_building_items = BuildingWithHistory.objects.filter(
            event_origin__source="import",
            event_origin__id__in=affected_bdtopo_import_ids,
            rnb_id__in=candidate_bdnb_history_items.values_list("rnb_id", flat=True),
            addresses_id__isnull=False,
        )

        for candidate_bdnb_history_item in candidate_bdnb_history_items:
            bdtopo_history_or_building_item = next(
                (
                    item
                    for item in bdtopo_history_or_building_items
                    if item.rnb_id == candidate_bdnb_history_item.rnb_id
                ),
                None,
            )
            if bdtopo_history_or_building_item:
                result.append(
                    BuildingHistoryItemPair(
                        rnb_id=candidate_bdnb_history_item.rnb_id,
                        bdtopo_history_or_building_item=bdtopo_history_or_building_item,
                        bdnb_history_item=candidate_bdnb_history_item,
                    )
                )

        return result
