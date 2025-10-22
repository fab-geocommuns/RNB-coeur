from datetime import datetime, timezone
from django.test import TestCase
from datetime import timedelta
from batid.models import Address
from batid.models import Building
from batid.models import BuildingImport
from batid.models import BuildingHistoryOnly
from batid.services.data_fix.fix_initial_addresses_attribution import (
    InitialAddressesAttributionDataFix,
)


def now():
    return datetime.now(timezone.utc)


class TestFixInitialAddressesAttribution(TestCase):
    def _create_building(self, rnb_id: str, event_origin: dict) -> None:
        Building.objects.create(
            rnb_id=rnb_id,
            event_origin=event_origin,
        )

    def _update_building(
        self, rnb_id: str, event_origin: dict, addresses_id: list[str]
    ) -> None:
        Building.objects.filter(rnb_id=rnb_id).update(
            event_origin=event_origin,
            addresses_id=addresses_id,
        )

    def setUp(self):
        three_days_ago = now() - timedelta(days=3)
        two_days_ago = now() - timedelta(days=2)
        correct_addresses_historisation_date = two_days_ago

        self.address1 = Address.objects.create(id="cle_interop_1")
        self.address2 = Address.objects.create(id="cle_interop_2")

        impacted_bdnb_import = BuildingImport.objects.create(
            import_source="bdnb_test",
            created_at=three_days_ago,
        )
        impacted_bdtopo_import = BuildingImport.objects.create(
            import_source="bdtopo_test",
            created_at=three_days_ago,
        )
        unimpacted_bdnb_import = BuildingImport.objects.create(
            import_source="bdnb_test",
            created_at=now(),  # after the correct addresses historisation date
        )
        unimpacted_bdtopo_import = BuildingImport.objects.create(
            import_source="bdtopo_test",
            created_at=now(),  # after the correct addresses historisation date
        )

        # Problematic case
        self._create_building(
            "need_fix", event_origin={"source": "import", "id": impacted_bdnb_import.id}
        )
        self._update_building(
            "need_fix",
            event_origin={
                "source": "import",
                "id": impacted_bdtopo_import.id,
            },
            addresses_id=[self.address1.id, self.address2.id],
        )
        self._update_building(
            "need_fix",
            event_origin={"source": "contribution", "id": 1},
            addresses_id=[self.address1.id],
        )
        self._update_building(
            "need_fix",
            event_origin={"source": "contribution", "id": 2},
            addresses_id=[self.address2.id],
        )
        # Not problematic case: building without addresses
        self._create_building(
            "ok_noaddress",
            event_origin={"source": "import", "id": impacted_bdnb_import.id},
        )
        self._update_building(
            "ok_noaddress",
            event_origin={"source": "import", "id": impacted_bdtopo_import.id},
            addresses_id=None,
        )
        # Not problematic case: building created manually
        self._create_building(
            "ok_manual", event_origin={"source": "contribution", "id": 1}
        )
        self._update_building(
            "ok_manual",
            event_origin={"source": "import", "id": impacted_bdtopo_import.id},
            addresses_id=[self.address1.id],
        )
        # Not problematic case: building created by non-impacted imports
        self._create_building(
            "ok_noimpact",
            event_origin={"source": "import", "id": unimpacted_bdnb_import.id},
        )
        self._update_building(
            "ok_noimpact",
            event_origin={"source": "import", "id": unimpacted_bdtopo_import.id},
            addresses_id=[self.address1.id],
        )

    def test_crashes_on_building_with_other_history_items_between_bdnb_and_bdtopo(self):
        raise NotImplementedError("Not implemented yet")

    def test_fixes_single_initial_addresses_attribution(self):
        fixer = InitialAddressesAttributionDataFix()
        fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(rnb_id="need_fix").addresses_id,
            [self.address1.id, self.address2.id],
        )

    def test_does_not_change_building_history_without_addresses(self):
        fixer = InitialAddressesAttributionDataFix()
        fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(rnb_id="ok_noaddress").addresses_id,
            None,
        )
        self.assertEqual(
            Building.objects.get(rnb_id="ok_noaddress").addresses_id,
            None,
        )

    def test_does_not_change_building_created_manually(self):
        fixer = InitialAddressesAttributionDataFix()
        fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(rnb_id="ok_manual").addresses_id,
            None,
        )
        self.assertEqual(
            Building.objects.get(rnb_id="ok_manual").addresses_id,
            [self.address1.id],
        )

    def test_does_not_change_building_created_by_non_impacted_imports(self):
        fixer = InitialAddressesAttributionDataFix()
        fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(rnb_id="ok_noimpact").addresses_id,
            None,
        )
        self.assertEqual(
            Building.objects.get(rnb_id="ok_noimpact").addresses_id,
            [self.address1.id],
        )
