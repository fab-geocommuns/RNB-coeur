from datetime import datetime

from django.test import TestCase

from batid.models import BuildingStatus, Candidate, Address, Building
from batid.services.candidate import Inspector
from batid.tests.helpers import (
    create_paris,
    create_constructed_bdg,
    coords_to_mp_geom,
    coords_to_point_geom,
)


class TestInspectorBdgCreate(TestCase):
    def setUp(self) -> None:
        # The city
        create_paris()

        # The candidate
        coords = [
            [2.349804906833981, 48.85789205519228],
            [2.349701279442314, 48.85786369735885],
            [2.3496535925009994, 48.85777922711969],
            [2.349861764341199, 48.85773095834841],
            [2.3499452164882086, 48.857847406681174],
            [2.349804906833981, 48.85789205519228],
        ]
        Candidate.objects.create(
            shape=coords_to_mp_geom(coords),
            source="bdnb",
            source_id="bdnb_1",
            address_keys=["add_1", "add_2"],
            is_light=False,
        )

        # Create the addresses
        Address.objects.create(
            id="add_1",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street_name="de Rivoli",
            street_type="rue",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )
        Address.objects.create(
            id="add_2",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street_rep="bis",
            street_name="de Rivoli",
            street_type="rue",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )

    def test_creation(self):
        i = Inspector()
        i.inspect()

        # Check we have zero not inspected candidates
        c_count = Candidate.objects.filter(inspected_at__isnull=True).count()
        self.assertEqual(c_count, 0)

        # Check we have only one building
        b_count = Building.objects.all().count()
        self.assertEqual(b_count, 1)

        # Check the building has two adresses
        b = Building.objects.all().first()
        self.assertEqual(b.addresses.count(), 2)
        addresses_ids = [a.id for a in b.addresses.all()]
        self.assertIn("add_1", addresses_ids)
        self.assertIn("add_2", addresses_ids)

        # Check the ext_ids are correct
        self.assertEqual(b.ext_bdnb_id, "bdnb_1")
        self.assertEqual(b.ext_bdtopo_id, "")


class TestInspectorBdgUpdate(TestCase):
    def setUp(self):
        # Create the city
        create_paris()

        # Create an existing building
        coords = [
            [2.349804906833981, 48.85789205519228],
            [2.349701279442314, 48.85786369735885],
            [2.3496535925009994, 48.85777922711969],
            [2.349861764341199, 48.85773095834841],
            [2.3499452164882086, 48.857847406681174],
            [2.349804906833981, 48.85789205519228],
        ]
        create_constructed_bdg("EXISTING", coords)

        # Create a candidate for the merge
        Candidate.objects.create(
            shape=coords_to_mp_geom(coords),
            source="bdnb",
            source_id="bdnb_1",
            address_keys=["add_1", "add_2"],
            is_light=False,
        )
        Candidate.objects.create(
            shape=coords_to_mp_geom(coords),
            source="bdtopo",
            source_id="bdtopo_1",
            address_keys=["add_1", "add_3"],
            is_light=False,
        )

        # Create the addresses
        Address.objects.create(
            id="add_1",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street_name="de Rivoli",
            street_type="rue",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )
        Address.objects.create(
            id="add_2",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street_rep="bis",
            street_name="de Rivoli",
            street_type="rue",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )
        Address.objects.create(
            id="add_3",
            source="ban",
            point=coords_to_point_geom(lng=2.3498853683277345, lat=48.85791913114588),
            street_number="39",
            street_name="de Rivoli",
            street_type="rue",
            city_name="Paris",
            city_zipcode="75004",
            city_insee_code="75104",
        )

    def test_merge(self):
        i = Inspector()
        i.inspect()

        # Check we have zero not inspected candidates
        c_count = Candidate.objects.filter(inspected_at__isnull=True).count()
        self.assertEqual(c_count, 0)

        # Check we have only one building
        b_count = Building.objects.all().count()
        self.assertEqual(b_count, 1)

        # Check the building has three adresses
        b = Building.objects.get(rnb_id="EXISTING")
        self.assertEqual(b.addresses.count(), 3)

        addresses_ids = [a.id for a in b.addresses.all()]
        self.assertIn("add_1", addresses_ids)
        self.assertIn("add_2", addresses_ids)
        self.assertIn("add_3", addresses_ids)

        # Check the ext_ids are correct
        self.assertEqual(b.ext_bdnb_id, "bdnb_1")
        self.assertEqual(b.ext_bdtopo_id, "bdtopo_1")