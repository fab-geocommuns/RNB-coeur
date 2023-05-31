import json
from datetime import datetime

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase

from batid.models import Building, BuildingStatus


class StatusTestCase(TestCase):
    def setUp(self):
        # One building with one status
        b = self._create_bdg("WITH-STATUS")

        happened_at = datetime(1975, 1, 1)
        BuildingStatus.objects.create(
            building=b,
            status="constructionProject",
            happened_at=happened_at,
            is_current=True,
        )

    def test_current_status(self):
        b = Building.objects.get(rnb_id="WITH-STATUS")
        self.assertEqual(b.current_status.status, "constructionProject")

    def test_current_replacement(self):
        b = self._create_bdg("TWO-STATUS")

        happened_at = datetime(1975, 1, 1)
        old_s = BuildingStatus.objects.create(
            building=b,
            status="constructionProject",
            happened_at=happened_at,
            is_current=True,
        )

        happened_at = datetime(1980, 1, 1)
        BuildingStatus.objects.create(
            building=b,
            status="constructed",
            happened_at=happened_at,
            is_current=True,
        )

        # The current status should be the most recent one, tagged with current
        self.assertEqual(b.current_status.status, "constructed")

        # Reload the old status
        old_s.refresh_from_db()
        self.assertEqual(old_s.is_current, False)

    def test_status_order(self):
        b = self._create_bdg("FOUR-STATUS")

        # Create the middle status
        happened_at = datetime(1980, 1, 1)
        BuildingStatus.objects.create(
            building=b,
            status="constructed",
            happened_at=happened_at,
            is_current=False,
        )

        # Create the newest status
        happened_at = datetime(2020, 1, 1)
        BuildingStatus.objects.create(
            building=b,
            status="demolished",
            happened_at=happened_at,
            is_current=True,
        )

        # Create the olest status (no happened_at)
        BuildingStatus.objects.create(
            building=b,
            status="constructionProject",
            is_current=False,
        )

        b.refresh_from_db()

        status = b.status.all()
        self.assertEqual(status[0].status, "constructionProject")
        self.assertEqual(status[1].status, "constructed")
        self.assertEqual(status[2].status, "demolished")

    def _create_bdg(self, rnb_id: str) -> Building:
        coords = {
            "coordinates": [
                [
                    [
                        [1.0654705955877262, 46.63423852982024],
                        [1.065454930919401, 46.634105152847496],
                        [1.0656648374661017, 46.63409009413692],
                        [1.0656773692001593, 46.63422131990677],
                        [1.0654705955877262, 46.63423852982024],
                    ]
                ]
            ],
            "type": "MultiPolygon",
        }
        geom = GEOSGeometry(json.dumps(coords), srid=4326)
        geom.transform(settings.DEFAULT_SRID)

        return Building.objects.create(
            rnb_id=rnb_id,
            source="dummy",
            shape=geom,
            point=geom.point_on_surface,
        )
