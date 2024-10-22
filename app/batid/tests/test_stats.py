import os

from django.test import TestCase

from batid.services.stats import get_path, all_stats, set_stat, clear_stats


class TestStats(TestCase):

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


    def test_key_must_be_str(self):

        # Start from empty slate
        clear_stats()

        # Try to set a non-string key
        with self.assertRaises(ValueError):
            set_stat(42, 42)

        # Check the file is still empty
        stats = all_stats()
        self.assertEqual(stats, {})
