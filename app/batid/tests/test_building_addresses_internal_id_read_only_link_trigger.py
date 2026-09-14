from batid.models import Address, Building, BuildingAddressesInternalIdReadOnly
from django.test import TransactionTestCase


class BuildingAddressesInternalIdReadOnlyLinkCase(TransactionTestCase):
    """Mirrors test_building_addresse_link_trigger.py: same
    keep_building_address_link_updated() trigger, extended to also maintain
    BuildingAddressesInternalIdReadOnly from addresses_internal_id."""

    def test_create_building(self):
        """Input: a building created with addresses_internal_id set to two
        addresses' internal_id values.
        Expected: the trigger inserts one BuildingAddressesInternalIdReadOnly row per
        address, on insert."""
        links_n = BuildingAddressesInternalIdReadOnly.objects.count()
        self.assertEqual(links_n, 0)

        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")

        b = Building.objects.create(
            rnb_id="1", addresses_internal_id=[a1.internal_id, a2.internal_id]
        )

        links = BuildingAddressesInternalIdReadOnly.objects.order_by("address_id")

        self.assertEqual(links.count(), 2)
        self.assertEqual(links[0].building_id, b.id)
        self.assertEqual(links[0].address_id, a1.internal_id)

        self.assertEqual(links[1].building_id, b.id)
        self.assertEqual(links[1].address_id, a2.internal_id)

    def test_update_building(self):
        """Input: a building created with no addresses_internal_id, then
        updated to reference two addresses.
        Expected: no link row before the update, two after — the trigger
        deletes and re-inserts on update, same as for addresses_id."""
        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")

        b = Building.objects.create(rnb_id="1")

        links_n = BuildingAddressesInternalIdReadOnly.objects.count()
        self.assertEqual(links_n, 0)

        b.addresses_internal_id = [a1.internal_id, a2.internal_id]
        b.save()

        links = BuildingAddressesInternalIdReadOnly.objects.order_by("address_id")

        self.assertEqual(links.count(), 2)
        self.assertEqual(links[0].building_id, b.id)
        self.assertEqual(links[0].address_id, a1.internal_id)

        self.assertEqual(links[1].building_id, b.id)
        self.assertEqual(links[1].address_id, a2.internal_id)

    def test_update_building_does_not_affect_other_join_table(self):
        """Input: a building linked through both addresses_id and
        addresses_internal_id, then updated on addresses_internal_id only.
        Expected: the addresses_id-based join table (BuildingAddressesReadOnly)
        is untouched, since only addresses_internal_id changed."""
        from batid.models import BuildingAddressesReadOnly

        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")

        b = Building.objects.create(
            rnb_id="1",
            addresses_id=[a1.id],
            addresses_internal_id=[a1.internal_id],
        )

        b.addresses_internal_id = [a1.internal_id, a2.internal_id]
        b.save()

        self.assertEqual(BuildingAddressesInternalIdReadOnly.objects.count(), 2)
        self.assertEqual(BuildingAddressesReadOnly.objects.count(), 1)

    def test_delete_building_is_forbidden_and_links_survive(self):
        """Input: a building linked to two addresses via addresses_internal_id.
        Expected: deletion is blocked (same postgres trigger as for
        addresses_id), and the internal_id-based links are left intact."""
        from batid.exceptions import ForbiddenDjangoNativeFunction

        a1 = Address.objects.create(id="address_1")
        a2 = Address.objects.create(id="address_2")

        Building.objects.create(
            rnb_id="1", addresses_internal_id=[a1.internal_id, a2.internal_id]
        )

        links_n = BuildingAddressesInternalIdReadOnly.objects.count()
        self.assertEqual(links_n, 2)

        b = Building.objects.get(rnb_id="1")
        with self.assertRaises(ForbiddenDjangoNativeFunction):
            b.delete()

        self.assertTrue(Building.objects.filter(rnb_id="1").exists())
        self.assertEqual(BuildingAddressesInternalIdReadOnly.objects.count(), 2)

    def test_create_building_with_non_existing_address_internal_id(self):
        """Input: a building created with an addresses_internal_id value that
        does not match any Address.internal_id.
        Expected: the FK on BuildingAddressesInternalIdReadOnly rejects the insert with
        an IntegrityError, same as the addresses_id path does against
        batid_address.id."""
        from django.db.utils import IntegrityError

        a1 = Address.objects.create(id="address_1")

        with self.assertRaises(IntegrityError):
            Building.objects.create(
                rnb_id="1", addresses_internal_id=[a1.internal_id, 999999999]
            )
