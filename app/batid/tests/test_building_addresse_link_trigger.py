from batid.models import Address, Building, BuildingAddressesReadOnly
from django.test import TransactionTestCase


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


class AddressDeletionTrigger(TransactionTestCase):
    def test_cannot_delete_address_linked_to_building(self):
        """Deleting an address that is currently linked to a building should raise an error."""
        from django.db.utils import InternalError

        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")

        Building.objects.create(rnb_id="1", addresses_id=[a1.id, a2.id])

        with self.assertRaises(InternalError):
            a1.delete()

        # The address should still exist
        self.assertTrue(Address.objects.filter(id="address_1").exists())

    def test_cannot_delete_address_referenced_in_history_only(self):
        """Deleting an address that is no longer linked to any current building
        but is still referenced in building history should raise an error."""
        from django.db.utils import InternalError

        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")

        # Create a building with both addresses
        b = Building.objects.create(rnb_id="1", addresses_id=[a1.id, a2.id])

        # Remove a1 from the building — this creates a history entry referencing a1
        b.addresses_id = [a2.id]
        b.save()

        # a1 is no longer in any current building, but is still in history
        with self.assertRaises(InternalError):
            a1.delete()

        self.assertTrue(Address.objects.filter(id="address_1").exists())

    def test_can_delete_address_never_linked_to_building(self):
        """Deleting an address that was never linked to any building should work fine."""
        a1 = Address.objects.create(id="address_1")

        a1.delete()

        self.assertFalse(Address.objects.filter(id="address_1").exists())
