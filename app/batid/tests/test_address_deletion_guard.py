from batid.models import Address, Building
from django.db import connection, transaction
from django.db.utils import InternalError
from django.test import TransactionTestCase


def delete_address(cle_interop: str) -> None:
    """DELETE straight in SQL: the deletion guard is a trigger on batid_address,
    and Django's own delete() would first remove the join table rows."""
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM batid_address WHERE cle_interop = %s;", [cle_interop]
        )


class AddressDeletionGuardTestCase(TransactionTestCase):
    """check_address_is_linked(), fired by prevent_delete_linked_address_trigger
    before every DELETE on batid_address. Its error messages are the only place
    where the trigger reads the BAN interop key of the deleted address."""

    def test_unlinked_address_is_deleted(self):
        """
        Input: an address no building refers to, current or past.
        Expected: it is deleted.
        """
        Address.objects.create(cle_interop="01001_0001_00001")

        delete_address("01001_0001_00001")

        self.assertFalse(
            Address.objects.filter(cle_interop="01001_0001_00001").exists()
        )

    def test_address_linked_to_a_building_is_kept(self):
        """
        Input: an address listed in addresses_internal_id of a current building.
        Expected: the deletion fails, the message names the address by its BAN
        interop key, and the address is still there.
        """
        address = Address.objects.create(cle_interop="01001_0001_00001")
        Building.objects.create(
            rnb_id="XYZ", addresses_internal_id=[address.internal_id]
        )

        with self.assertRaisesMessage(
            InternalError,
            "Cannot delete address 01001_0001_00001 because it is referenced by a building",
        ):
            with transaction.atomic():
                delete_address("01001_0001_00001")

        self.assertTrue(Address.objects.filter(cle_interop="01001_0001_00001").exists())

    def test_address_linked_in_building_history_only_is_kept(self):
        """
        Input: an address that a building referenced in a previous version, and
        that its current version does not reference anymore.
        Expected: the deletion fails, the message names the address by its BAN
        interop key, and the address is still there.
        """
        address = Address.objects.create(cle_interop="01001_0001_00001")
        building = Building.objects.create(
            rnb_id="XYZ", addresses_internal_id=[address.internal_id]
        )
        building.addresses_internal_id = []
        building.save()

        with self.assertRaisesMessage(
            InternalError,
            "Cannot delete address 01001_0001_00001 because it is referenced in building history",
        ):
            with transaction.atomic():
                delete_address("01001_0001_00001")

        self.assertTrue(Address.objects.filter(cle_interop="01001_0001_00001").exists())
