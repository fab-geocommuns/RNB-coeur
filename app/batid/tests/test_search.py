from django.test import TestCase
from batid.tests.utils.factory import BuildingFactory, AddressAutransFactory
from batid.models import Building, Address


def create_village():
    # village built from select * from batid_building bb where st_dwithin(shape, st_transform(st_point(5.5254949, 45.1273093, 4326), 2154), 30);
    building_1 = BuildingFactory(
        rnb_id="2MG793YGTMHG",
        point="SRID=2154;POINT (898502.7366666667 6450731)",
        shape="SRID=2154;MULTIPOLYGON (((898508.4 6450725.8, 898496.1 6450727.2, 898496.9 6450736.2, 898509.5 6450734.8, 898508.4 6450725.8)))",
    )

    address_1 = AddressAutransFactory(
        street_number="20",
        street_name="des narces",
        street_type="route",
    )

    building_1.addresses.add(address_1)

    # building_2 has no address
    BuildingFactory(
        rnb_id="73M7EQ3WEK97",
        point="SRID=2154;POINT (898510.2779411766 6450722.95)",
        shape="SRID=2154;MULTIPOLYGON (((898508.4 6450725.8, 898512.8 6450725.2, 898512.1 6450720.1, 898507.8 6450720.7, 898508.4 6450725.8)))",
    )

    building_3 = BuildingFactory(
        rnb_id="V1DNA2FGPCWF",
        point="SRID=2154;POINT (898556.2241749174 6450735.5)",
        shape="SRID=2154;MULTIPOLYGON (((898567.9 6450748.5, 898564.4 6450718.2, 898554.3 6450719.5, 898549.7 6450722.8, 898545.3 6450726.1, 898545.8 6450732.9, 898546.3 6450738.1, 898546.6 6450740.5, 898547 6450742.5, 898547.3 6450743.7, 898547.7 6450744.6, 898548.3 6450745.2, 898549 6450746, 898549.6 6450746.8, 898550.2 6450747.3, 898551.1 6450748, 898551.9 6450748.5, 898552.3 6450748.7, 898553.2 6450749.1, 898554.6 6450749.4, 898556 6450749.8, 898557.6 6450749.7, 898567.9 6450748.5)))",
    )

    address_3 = AddressAutransFactory(
        street_number="91",
        street_name="des mateaux",
        street_type="rue",
    )

    building_3.addresses.add(address_3)


class TestSearch(TestCase):
    def test_search(self):
        create_village()

        assert len(Building.objects.all()) == 3
