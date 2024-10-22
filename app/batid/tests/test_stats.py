import os
from abc import ABC
from datetime import datetime
from unittest.mock import patch

from django.test import TestCase

from batid.models import Building
from batid.services.stats import get_path, all_stats, set_stat, clear_stats, fetch_stats, get_stat, \
    ACTIVE_BUILDING_COUNT


class AbstractStatTests(ABC, TestCase):

    """
    This abstract class is made to mock the cached_stat file path in all tests.
    This way, we do not risk to write in the real file.
    """

    def setUp(cls):
        cls.patcher = patch("batid.services.source.Source.default_ref")
        cls.mock_ref = cls.patcher.start()
        cls.mock_ref.return_value = {"cached_stats": {"filename": "test_cached_stats.json"}}

    def tearDown(cls):
        # Stop the patcher (https://docs.python.org/3/library/unittest.mock.html#patch-methods-start-and-stop)
        cls.patcher.stop()
        # Remove the tmp stat file
        clear_stats()



class TestStatsHelper(AbstractStatTests):

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
        self.assertEqual(stats["life_meaning"]["value"], 42)
        self.assertIsInstance(stats["life_meaning"]["calculated_at"], datetime)


    def test_update_one_key(self):

        # Start from empty slate
        clear_stats()

        # Set one value
        set_stat("life_meaning", 42)
        # Check the value
        stats = all_stats()
        self.assertEqual(stats["life_meaning"]["value"], 42)
        first_calculated_at = stats["life_meaning"]["calculated_at"]

        # Update the value
        set_stat("life_meaning", 43)
        # Check again the value
        stats = all_stats()
        self.assertEqual(stats["life_meaning"]["value"], 43)
        second_calculated_at = stats["life_meaning"]["calculated_at"]

        # Verify the calculated_at has been updated
        self.assertGreater(second_calculated_at, first_calculated_at)


    def test_get_stat(self):

        # Start from empty slate
        clear_stats()

        # Set one value
        set_stat("life_meaning", 42)

        # Read it
        stat = get_stat("life_meaning")
        self.assertEqual(stat["value"], 42)
        self.assertIsInstance(stat["calculated_at"], datetime)

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


class TestStatsFetching(AbstractStatTests):

    def setUp(self):

        super().setUp()

        # Data for testing active building count
        Building.objects.all().delete()
        Building.objects.create(rnb_id="1234", is_active=True)
        Building.objects.create(rnb_id="ABCD", is_active=True)
        Building.objects.create(rnb_id="WXYZ", is_active=False)

    def test_active_building_count(self):

        fetch_stats()
        stat = get_stat(ACTIVE_BUILDING_COUNT)
        self.assertEqual(stat["value"], 2)




