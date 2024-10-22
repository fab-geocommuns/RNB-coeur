import os

from django.test import TestCase

from batid.models import Building
from batid.services.stats import get_path, all_stats, set_stat, clear_stats, fetch_stats, get_stat, \
    ACTIVE_BUILDING_COUNT


class TestStatsHelper(TestCase):

    def test_create_if_needed(self):

        # Remove the file
        clear_stats()

        # Get the file path and check it does not exist
        src_path = get_path()
        self.assertFalse(os.path.exists(src_path))

        # Try to read it
        stats = all_stats()

        # Check the file is created and filled with an empty dict
        self.assertTrue(os.path.exists(src_path))
        self.assertEqual(stats, {})


    def test_set_one_key(self):

        # Start from empty slate
        clear_stats()

        # Set one value
        set_stat("life_meaning", 42)

        # Read it
        stats = all_stats()
        self.assertDictEqual(stats, {"life_meaning": 42})


    def test_update_one_key(self):

        # Start from empty slate
        clear_stats()

        # Set one value
        set_stat("life_meaning", 42)
        # Check the value
        stats = all_stats()
        self.assertDictEqual(stats, {"life_meaning": 42})

        # Update the value
        set_stat("life_meaning", 43)
        # Check again the value
        stats = all_stats()
        self.assertDictEqual(stats, {"life_meaning": 43})


    def test_get_stat(self):

        # Start from empty slate
        clear_stats()

        # Set one value
        set_stat("life_meaning", 42)

        # Read it
        value = get_stat("life_meaning")
        self.assertEqual(value, 42)

    def test_key_must_be_str(self):

        # Start from empty slate
        clear_stats()

        # ##################
        # Write test

        # Try to set a non-string key
        with self.assertRaises(ValueError):
            set_stat(42, 42)

        # Check the file is still empty
        stats = all_stats()
        self.assertEqual(stats, {})

        # ##################
        # Read test

        # Try to read a non-string key
        with self.assertRaises(ValueError):
            get_stat(42)


class TestStatsFetching(TestCase):

    def setUp(self):

        # Data for testing active building count
        Building.objects.all().delete()
        Building.objects.create(rnb_id="1234", is_active=True)
        Building.objects.create(rnb_id="ABCD", is_active=True)
        Building.objects.create(rnb_id="WXYZ", is_active=False)

    def test_active_building_count(self):

        fetch_stats()
        self.assertEqual(get_stat(ACTIVE_BUILDING_COUNT), 2)





