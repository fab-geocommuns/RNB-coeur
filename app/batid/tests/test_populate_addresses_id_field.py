from django.test import TransactionTestCase

from batid.models import Address
from batid.models import Building
from batid.models import BuildingAddressesReadOnly
from batid.services.populate_addresses_id_field import launch_procedure


class TestPopulateAddressesIdField(TransactionTestCase):
    def test_data_migration(self):
        # create addresses
        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")
        a3 = Address.objects.create(id="address_3")

        # create buildings with linked addresses through the old MTM relationship
        b1 = Building.objects.create(rnb_id="1")
        b1.addresses.set([a1, a2, a3])

        b2 = Building.objects.create(rnb_id="2")
        b2.addresses.set([a1])

        b3 = Building.objects.create(rnb_id="3")
        b3.addresses.set([a2, a3])

        # building withtout address
        b4 = Building.objects.create(rnb_id="4")

        # BuildingAddressesReadOnly is empty before the data migration
        read_only_links = BuildingAddressesReadOnly.objects.all()
        self.assertEqual(read_only_links.count(), 0)

        launch_procedure()

        # addresses_id field is populated
        b1 = Building.objects.get(rnb_id="1")
        b1.addresses_id.sort()
        self.assertEqual(b1.addresses_id, [a1.id, a2.id, a3.id])

        b2 = Building.objects.get(rnb_id="2")
        self.assertEqual(b2.addresses_id, [a1.id])

        b3 = Building.objects.get(rnb_id="3")
        b3.addresses_id.sort()
        self.assertEqual(b3.addresses_id, [a2.id, a3.id])

        b4 = Building.objects.get(rnb_id="4")
        self.assertEqual(b4.addresses_id, [])

        # BuildingAddressesReadOnly is populated (through the trigger)
        read_only_links = BuildingAddressesReadOnly.objects.all().order_by(
            "building_id", "address_id"
        )
        self.assertEqual(read_only_links.count(), 6)
        self.assertEqual(
            (read_only_links[0].building_id, read_only_links[0].address_id),
            (b1.id, a1.id),
        )
        self.assertEqual(
            (read_only_links[1].building_id, read_only_links[1].address_id),
            (b1.id, a2.id),
        )
        self.assertEqual(
            (read_only_links[2].building_id, read_only_links[2].address_id),
            (b1.id, a3.id),
        )

        self.assertEqual(
            (read_only_links[3].building_id, read_only_links[3].address_id),
            (b2.id, a1.id),
        )

        self.assertEqual(
            (read_only_links[4].building_id, read_only_links[4].address_id),
            (b3.id, a2.id),
        )
        self.assertEqual(
            (read_only_links[5].building_id, read_only_links[5].address_id),
            (b3.id, a3.id),
        )
