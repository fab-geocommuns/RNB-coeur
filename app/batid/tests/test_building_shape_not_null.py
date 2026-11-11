from batid.models.building import Building
from django.contrib.gis.geos import GEOSGeometry
from django.db import IntegrityError, transaction
from django.test import TestCase


class BuildingShapeNotNullTestCase(TestCase):
    def test_building_without_shape_is_refused(self):
        """
        Input: insert a building with a NULL shape, then set the shape of an existing
        building to NULL.
        Expected: both writes fail with an IntegrityError (batid_building.shape is
        NOT NULL); the existing building keeps its shape.
        """
        with self.assertRaises(IntegrityError), transaction.atomic():
            Building.objects.create(
                rnb_id="NOSHAPENOSHA", shape=None, status="constructed"
            )

        point = GEOSGeometry("POINT(2.35 48.85)", srid=4326)
        Building.objects.create(rnb_id="WITHSHAPEBDG", shape=point, point=point)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Building.objects.filter(rnb_id="WITHSHAPEBDG").update(shape=None)

        self.assertEqual(Building.objects.get(rnb_id="WITHSHAPEBDG").shape, point)
