from datetime import datetime, timezone
from django.test import TestCase
from datetime import timedelta
from batid.models import Address
from batid.models import Building
from batid.models import BuildingImport
from batid.models import BuildingHistoryOnly
from batid.models import BuildingWithHistory
from batid.services.data_fix.fix_initial_addresses_attribution import (
    InitialAddressesAttributionDataFix,
)


def now():
    return datetime.now(timezone.utc)


class TestFixInitialAddressesAttribution(TestCase):
    def _create_import(
        self, import_source: str, created_at: datetime
    ) -> BuildingImport:
        new_import = BuildingImport.objects.create(
            import_source=import_source,
        )
        new_import.created_at = created_at
        BuildingImport.objects.bulk_update([new_import], ["created_at"])
        return new_import

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

        self.impacted_bdnb_import = self._create_import("bdnb_test", three_days_ago)
        self.impacted_bdtopo_import = self._create_import("bdtopo_test", three_days_ago)

        self.fixer = InitialAddressesAttributionDataFix(
            correct_addresses_historisation_date=correct_addresses_historisation_date,
        )

    def test_ignores_on_building_with_other_history_items_between_bdnb_and_bdtopo(self):
        self._create_building(
            "problematic",
            event_origin={"source": "import", "id": self.impacted_bdnb_import.id},
        )
        self._update_building(
            "problematic",
            event_origin={"source": "contribution", "id": 1},
            addresses_id=[self.address1.id],
        )
        self._update_building(
            "problematic",
            event_origin={"source": "import", "id": self.impacted_bdtopo_import.id},
            addresses_id=[self.address2.id],
        )
        self.fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(
                rnb_id="problematic",
                event_origin={"source": "import", "id": self.impacted_bdnb_import.id},
            ).addresses_id,
            None,
        )
        self.assertEqual(
            BuildingWithHistory.objects.get(
                rnb_id="problematic", event_origin={"source": "contribution", "id": 1}
            ).addresses_id,
            [self.address1.id],
        )
        self.assertEqual(
            BuildingWithHistory.objects.get(
                rnb_id="problematic",
                event_origin={"source": "import", "id": self.impacted_bdtopo_import.id},
            ).addresses_id,
            [self.address2.id],
        )

    def test_fixes_single_initial_addresses_attribution_in_simple_case(self):
        # Problematic case with no subsequent update
        self._create_building(
            "need_fix1",
            event_origin={"source": "import", "id": self.impacted_bdnb_import.id},
        )
        self._update_building(
            "need_fix1",
            event_origin={
                "source": "import",
                "id": self.impacted_bdtopo_import.id,
            },
            addresses_id=[self.address1.id, self.address2.id],
        )
        self.fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(rnb_id="need_fix1").addresses_id,
            [self.address1.id, self.address2.id],
        )
        self.assertEqual(
            BuildingWithHistory.objects.get(
                rnb_id="need_fix1",
                event_origin={"source": "import", "id": self.impacted_bdtopo_import.id},
            ).addresses_id,
            [self.address1.id, self.address2.id],
        )

    def test_fixes_single_initial_addresses_attribution_in_case_with_subsequent_updates(
        self,
    ):
        self._create_building(
            "need_fix2",
            event_origin={"source": "import", "id": self.impacted_bdnb_import.id},
        )
        self._update_building(
            "need_fix2",
            event_origin={
                "source": "import",
                "id": self.impacted_bdtopo_import.id,
            },
            addresses_id=[self.address1.id, self.address2.id],
        )
        self._update_building(
            "need_fix2",
            event_origin={
                "source": "contribution",
                "id": 1,
            },
            addresses_id=[self.address2.id],
        )
        self.fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(
                rnb_id="need_fix2",
                event_origin={"source": "import", "id": self.impacted_bdnb_import.id},
            ).addresses_id,
            [self.address1.id, self.address2.id],
        )
        self.assertEqual(
            BuildingHistoryOnly.objects.get(
                rnb_id="need_fix2",
                event_origin={"source": "import", "id": self.impacted_bdtopo_import.id},
            ).addresses_id,
            [self.address1.id, self.address2.id],
        )
        self.assertEqual(
            BuildingWithHistory.objects.get(
                rnb_id="need_fix2",
                event_origin={"source": "contribution", "id": 1},
            ).addresses_id,
            [self.address2.id],
        )

    def test_fixes_initial_addresses_attribution_when_more_than_one_bdnb_update(self):
        self._create_building(
            "need_fix3",
            event_origin={"source": "import", "id": self.impacted_bdnb_import.id},
        )
        self._update_building(
            "need_fix3",
            event_origin={"source": "import", "id": self.impacted_bdnb_import.id},
            addresses_id=[],
        )
        self._update_building(
            "need_fix3",
            event_origin={"source": "import", "id": self.impacted_bdtopo_import.id},
            addresses_id=[self.address1.id, self.address2.id],
        )

    def test_does_not_change_building_history_without_addresses(self):
        # Not problematic case: building without addresses
        self._create_building(
            "ok_noaddress",
            event_origin={"source": "import", "id": self.impacted_bdnb_import.id},
        )
        self._update_building(
            "ok_noaddress",
            event_origin={"source": "import", "id": self.impacted_bdtopo_import.id},
            addresses_id=None,
        )
        self.fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(rnb_id="ok_noaddress").addresses_id,
            None,
        )
        self.assertEqual(
            Building.objects.get(rnb_id="ok_noaddress").addresses_id,
            None,
        )

    def test_does_not_change_building_created_manually(self):
        # Not problematic case: building created manually
        self._create_building(
            "ok_manual", event_origin={"source": "contribution", "id": 1}
        )
        self._update_building(
            "ok_manual",
            event_origin={"source": "import", "id": self.impacted_bdtopo_import.id},
            addresses_id=[self.address1.id],
        )
        self.fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(rnb_id="ok_manual").addresses_id,
            None,
        )
        self.assertEqual(
            Building.objects.get(rnb_id="ok_manual").addresses_id,
            [self.address1.id],
        )

    def test_does_not_change_building_created_by_non_impacted_imports(self):
        after_correct_addresses_historisation_date = now()
        unimpacted_bdnb_import = self._create_import(
            "bdnb_test", after_correct_addresses_historisation_date
        )
        unimpacted_bdtopo_import = self._create_import(
            "bdtopo_test", after_correct_addresses_historisation_date
        )
        self._create_building(
            "ok_noimpact",
            event_origin={"source": "import", "id": unimpacted_bdnb_import.id},
        )
        self._update_building(
            "ok_noimpact",
            event_origin={"source": "import", "id": unimpacted_bdtopo_import.id},
            addresses_id=[self.address1.id],
        )
        self.fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(rnb_id="ok_noimpact").addresses_id,
            None,
        )
        self.assertEqual(
            Building.objects.get(rnb_id="ok_noimpact").addresses_id,
            [self.address1.id],
        )
