from datetime import datetime, timezone
from django.test import TestCase
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
        address1 = Address.objects.create(id="cle_interop_1")
        address2 = Address.objects.create(id="cle_interop_2")
        bdnb_import = BuildingImport.objects.create(
            import_source="bdnb_test",
            created_at=now(),
        )
        bdtopo_import = BuildingImport.objects.create(
            import_source="bdtopo_test",
            created_at=now(),
        )
        self._create_building(
            "need_fix", event_origin={"source": "import", "id": bdnb_import.id}
        )
        self._update_building(
            "need_fix",
            event_origin={
                "source": "import",
                "id": bdtopo_import.id,
            },
            addresses_id=[address1.id, address2.id],
        )
        self._create_building(
            "ok_noaddress", event_origin={"source": "import", "id": bdnb_import.id}
        )
        self._update_building(
            "ok_noaddress",
            event_origin={"source": "import", "id": bdtopo_import.id},
            addresses_id=[],
        )
        self._create_building(
            "ok_manual", event_origin={"source": "contribution", "id": 1}
        )
        self._update_building(
            "ok_manual",
            event_origin={"source": "import", "id": bdtopo_import.id},
            addresses_id=[address1.id],
        )

    def test_fixes_single_initial_addresses_attribution(self):
        fixer = InitialAddressesAttributionDataFix()
        fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(rnb_id="needsfix").addresses_id,
            [address1.id, address2.id],
        )

    def test_does_not_change_building_history_without_addresses(self):
        fixer = InitialAddressesAttributionDataFix()
        fixer.fix_all()
        self.assertEqual(
            BuildingHistoryOnly.objects.get(rnb_id="oknoaddress1").addresses_id,
            [],
        )
        self.assertEqual(
            Building.objects.get(rnb_id="oknoaddress1").addresses_id,
            [],
        )
