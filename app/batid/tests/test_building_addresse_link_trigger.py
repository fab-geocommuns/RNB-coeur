from django.test import TestCase
from django.test import TransactionTestCase

from batid.models import Address
from batid.models import Building
from batid.models import BuildingAddressesReadOnly


class BuildingAddressLinkCase(TransactionTestCase):
    def test_create_building(self):
        links_n = BuildingAddressesReadOnly.objects.count()
        self.assertEqual(links_n, 0)

        # create addresses
        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")

        # create a building with linked addresses
        b = Building.objects.create(rnb_id="1", addresses_id=[a1.id, a2.id])

        # check the postgres trigger created the link
        links = BuildingAddressesReadOnly.objects.all()

        self.assertEqual(links.count(), 2)
        self.assertEqual(links[0].building_id, b.id)
        self.assertEqual(links[0].address_id, a1.id)

        self.assertEqual(links[1].building_id, b.id)
        self.assertEqual(links[1].address_id, a2.id)

    def test_update_building(self):
        # create addresses
        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")

        b = Building.objects.create(rnb_id="1")

        # no link has been created
        links_n = BuildingAddressesReadOnly.objects.count()
        self.assertEqual(links_n, 0)

        # update the building with linked addresses
        b.addresses_id = [a1.id, a2.id]
        b.save()

        links = BuildingAddressesReadOnly.objects.all()

        self.assertEqual(links.count(), 2)
        self.assertEqual(links[0].building_id, b.id)
        self.assertEqual(links[0].address_id, a1.id)

        self.assertEqual(links[1].building_id, b.id)
        self.assertEqual(links[1].address_id, a2.id)

    def test_delete_building(self):
        # create addresses
        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")

        # create a building with linked addresses
        b = Building.objects.create(rnb_id="1", addresses_id=[a1.id, a2.id])

        links_n = BuildingAddressesReadOnly.objects.count()
        self.assertEqual(links_n, 2)

        b.delete()

        # deletion of the building triggers the deletion of the links
        links_n = BuildingAddressesReadOnly.objects.count()
        self.assertEqual(links_n, 0)

    def test_create_building_with_non_existing_address(self):
        from django.db.utils import IntegrityError

        a1 = Address.objects.create(id="address_1")

        with self.assertRaises(IntegrityError):
            Building.objects.create(
                rnb_id="1", addresses_id=[a1.id, "salut je suis un hacker ahahah"]
            )

    def test_update_building_with_non_existing_address(self):
        from django.db.utils import IntegrityError

        a1 = Address.objects.create(id="address_1")
        b = Building.objects.create(rnb_id="1", addresses_id=[a1.id])

        with self.assertRaises(IntegrityError):
            b.addresses_id = [a1.id, "salut je suis un hacker ahahah"]
            b.save()


class AddressDeletionTrigger(TestCase):
    def test_delete_address(self):
        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")

        b1 = Building.objects.create(rnb_id="1", addresses_id=[a1.id, a2.id])
        b2 = Building.objects.create(rnb_id="2", addresses_id=[a1.id])
        b3 = Building.objects.create(rnb_id="3", addresses_id=[a2.id])

        links_n = BuildingAddressesReadOnly.objects.count()
        self.assertEqual(links_n, 4)

        # the address is deleted
        a1.delete()

        # the building should have been updated by the trigger, only a2 should be left
        b1 = Building.objects.get(rnb_id="1")
        self.assertEqual(b1.addresses_id, [a2.id])

        b2 = Building.objects.get(rnb_id="2")
        self.assertEqual(b2.addresses_id, [])

        b3 = Building.objects.get(rnb_id="3")
        self.assertEqual(b3.addresses_id, [a2.id])

        # the update of the buildings should have triggered the deletion of the links
        links = BuildingAddressesReadOnly.objects.all().order_by("building_id")
        self.assertEqual(links.count(), 2)
        self.assertEqual(links[0].building_id, b1.id)
        self.assertEqual(links[0].address_id, a2.id)
        self.assertEqual(links[1].building_id, b3.id)
        self.assertEqual(links[1].address_id, a2.id)
