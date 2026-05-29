from batid.models import Building, BuildingValidatedByReadOnly
from django.contrib.auth.models import User
from django.test import TransactionTestCase


class BuildingValidatedByLinkCase(TransactionTestCase):
    def test_create_building_with_validated_by(self):
        """
        Input: a building is created with two users in validated_by.
        Expected: the postgres trigger inserts a row in BuildingValidatedByReadOnly
        for each user.
        """
        links_n = BuildingValidatedByReadOnly.objects.count()
        self.assertEqual(links_n, 0)

        u1 = User.objects.create_user("alice", email="alice@example.com")
        u2 = User.objects.create_user("bob", email="bob@example.com")

        b = Building.objects.create(rnb_id="1", validated_by=[u1.id, u2.id])

        links = BuildingValidatedByReadOnly.objects.order_by("user_id")

        self.assertEqual(links.count(), 2)
        self.assertEqual(links[0].building_id, b.id)
        self.assertEqual(links[0].user_id, u1.id)

        self.assertEqual(links[1].building_id, b.id)
        self.assertEqual(links[1].user_id, u2.id)

    def test_create_building_with_empty_validated_by(self):
        """
        Input: a building is created with an empty validated_by list (the default).
        Expected: no link is created in BuildingValidatedByReadOnly.
        """
        b = Building.objects.create(rnb_id="1")

        self.assertEqual(b.validated_by, [])
        self.assertEqual(BuildingValidatedByReadOnly.objects.count(), 0)

    def test_update_building_add_users(self):
        """
        Input: an existing building has its validated_by updated to include users.
        Expected: the trigger creates a link for each user added.
        """
        u1 = User.objects.create_user("alice", email="alice@example.com")
        u2 = User.objects.create_user("bob", email="bob@example.com")

        b = Building.objects.create(rnb_id="1")
        self.assertEqual(BuildingValidatedByReadOnly.objects.count(), 0)

        b.validated_by = [u1.id, u2.id]
        b.save()

        links = BuildingValidatedByReadOnly.objects.order_by("user_id")

        self.assertEqual(links.count(), 2)
        self.assertEqual(links[0].building_id, b.id)
        self.assertEqual(links[0].user_id, u1.id)

        self.assertEqual(links[1].building_id, b.id)
        self.assertEqual(links[1].user_id, u2.id)

    def test_update_building_remove_one_user(self):
        """
        Input: a building has two users in validated_by; one is removed by saving
        a shorter array.
        Expected: only the link for the remaining user persists in the through table.
        """
        u1 = User.objects.create_user("alice", email="alice@example.com")
        u2 = User.objects.create_user("bob", email="bob@example.com")

        b = Building.objects.create(rnb_id="1", validated_by=[u1.id, u2.id])
        self.assertEqual(BuildingValidatedByReadOnly.objects.count(), 2)

        b.validated_by = [u1.id]
        b.save()

        links = BuildingValidatedByReadOnly.objects.all()
        self.assertEqual(links.count(), 1)
        self.assertEqual(links[0].building_id, b.id)
        self.assertEqual(links[0].user_id, u1.id)

    def test_update_building_clear_with_empty_list(self):
        """
        Input: validated_by is updated from a non-empty list to an empty list.
        Expected: all existing links for the building are deleted by the trigger.
        """
        u1 = User.objects.create_user("alice", email="alice@example.com")
        u2 = User.objects.create_user("bob", email="bob@example.com")

        b = Building.objects.create(rnb_id="1", validated_by=[u1.id, u2.id])
        self.assertEqual(BuildingValidatedByReadOnly.objects.count(), 2)

        b.validated_by = []
        b.save()

        self.assertEqual(BuildingValidatedByReadOnly.objects.count(), 0)

    def test_update_building_clear_with_none(self):
        """
        Input: validated_by is updated from a non-empty list to None.
        Expected: all existing links for the building are deleted by the trigger.
        """
        u1 = User.objects.create_user("alice", email="alice@example.com")

        b = Building.objects.create(rnb_id="1", validated_by=[u1.id])
        self.assertEqual(BuildingValidatedByReadOnly.objects.count(), 1)

        b.validated_by = None
        b.save()

        self.assertEqual(BuildingValidatedByReadOnly.objects.count(), 0)

    def test_create_building_with_non_existing_user(self):
        """
        Input: a building is created with a user id that does not exist.
        Expected: the trigger's insert into the through table fails with an IntegrityError
        because the foreign key to User is violated.
        """
        from django.db.utils import IntegrityError

        u1 = User.objects.create_user("alice", email="alice@example.com")

        with self.assertRaises(IntegrityError):
            Building.objects.create(rnb_id="1", validated_by=[u1.id, 99999999])

    def test_update_building_with_non_existing_user(self):
        """
        Input: an existing building's validated_by is updated to include a user
        id that does not exist.
        Expected: the trigger's insert into the through table fails with an IntegrityError.
        """
        from django.db.utils import IntegrityError

        u1 = User.objects.create_user("alice", email="alice@example.com")
        b = Building.objects.create(rnb_id="1", validated_by=[u1.id])

        with self.assertRaises(IntegrityError):
            b.validated_by = [u1.id, 99999999]
            b.save()

    def test_create_building_with_duplicate_user(self):
        """
        Input: a building is created with the same user id repeated in
        validated_by.
        Expected: the trigger tries to insert the same (building, user) pair twice and
        violates the unique_together constraint, raising an IntegrityError.
        """
        from django.db.utils import IntegrityError

        u1 = User.objects.create_user("alice", email="alice@example.com")

        with self.assertRaises(IntegrityError):
            Building.objects.create(rnb_id="1", validated_by=[u1.id, u1.id])

    def test_update_building_with_duplicate_user(self):
        """
        Input: an existing building is updated to have the same user id repeated in
        validated_by.
        Expected: the trigger tries to insert the same (building, user) pair twice and
        violates the unique_together constraint, raising an IntegrityError.
        """
        from django.db.utils import IntegrityError

        u1 = User.objects.create_user("alice", email="alice@example.com")
        b = Building.objects.create(rnb_id="1")

        with self.assertRaises(IntegrityError):
            b.validated_by = [u1.id, u1.id]
            b.save()

    def test_same_array_does_not_recreate_links(self):
        """
        Input: a building is saved again with the exact same validated_by content.
        Expected: the trigger only fires the DELETE/INSERT branch when the array actually
        changes; the link rows keep their original ids.
        """
        u1 = User.objects.create_user("alice", email="alice@example.com")

        b = Building.objects.create(rnb_id="1", validated_by=[u1.id])
        original_link_id = BuildingValidatedByReadOnly.objects.get(
            building_id=b.id, user_id=u1.id
        ).id

        b.validated_by = [u1.id]
        b.save()

        link = BuildingValidatedByReadOnly.objects.get(
            building_id=b.id, user_id=u1.id
        )
        self.assertEqual(link.id, original_link_id)


class UserValidatedByDeletionCase(TransactionTestCase):
    def test_cannot_delete_user_linked_to_building(self):
        """
        Input: a user is referenced in a building's validated_by and the
        corresponding through-row exists.
        Expected: deleting the user raises (ProtectedError) because the foreign key
        from BuildingValidatedByReadOnly to User uses on_delete=PROTECT.
        """
        from django.db.models import ProtectedError

        u1 = User.objects.create_user("alice", email="alice@example.com")
        Building.objects.create(rnb_id="1", validated_by=[u1.id])

        with self.assertRaises(ProtectedError):
            u1.delete()

        self.assertTrue(User.objects.filter(pk=u1.pk).exists())

    def test_can_delete_user_never_linked(self):
        """
        Input: a user who has never been added to any building's validated_by.
        Expected: deletion succeeds.
        """
        u1 = User.objects.create_user("alice", email="alice@example.com")
        u1.delete()

        self.assertFalse(User.objects.filter(username="alice").exists())

    def test_can_delete_user_after_being_removed_from_array(self):
        """
        Input: a user was in a building's validated_by, then removed from the
        array (which deletes the through-row via the trigger).
        Expected: the user can now be deleted because no through-row references them.
        """
        u1 = User.objects.create_user("alice", email="alice@example.com")
        b = Building.objects.create(rnb_id="1", validated_by=[u1.id])

        b.validated_by = []
        b.save()

        u1.delete()
        self.assertFalse(User.objects.filter(username="alice").exists())
