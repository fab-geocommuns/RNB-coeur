from django.test import TestCase

from api_alpha.serializers.serializers import BuildingGeoJSONSerializer
from api_alpha.serializers.serializers import BuildingSerializer


class GeoJSONSerializer(TestCase):
    def test_same_fields(self):
        """
        This test ensures that the fields included in the GeoJSON representation
        of a building are the same as those in the regular representation,
        except for the shape and point fields.

        We may forget to update both serializers in future development.
        """

        # make a copy of BuildingSerializer.Meta.fields
        reference_fields = BuildingSerializer.Meta.fields.copy()

        reference_fields.remove("shape")
        reference_fields.remove("point")

        geojson_fields = BuildingGeoJSONSerializer.Meta.fields

        self.assertEqual(set(geojson_fields), set(reference_fields))
