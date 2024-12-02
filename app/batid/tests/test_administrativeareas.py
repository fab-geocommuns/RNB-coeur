from django.test import TestCase

from batid.services.administrative_areas import com_list, validate_dpt_code, slice_dpts
from batid.services.administrative_areas import dpt_list_metropole
from batid.services.administrative_areas import dpt_list_overseas
from batid.services.administrative_areas import dpt_name
from batid.services.administrative_areas import dpts_list


class AdminAreas(TestCase):
    def test_length_and_names(self):

        metropole_list = dpt_list_metropole()
        self.assertEqual(len(metropole_list), 96)

        drom_list = dpt_list_overseas()
        self.assertEqual(len(drom_list), 5)

        com_overseas_list = com_list()
        self.assertEqual(len(com_overseas_list), 5)

        all = dpts_list()
        self.assertEqual(len(all), 106)

        # Test everybody has a name
        for code in all:
            try:
                dpt_name(code)
            except KeyError:
                self.fail(f"Missing name for {code}")

    def test_wrong_dpt(self):

        dpt = "1337"
        exists = validate_dpt_code(dpt)

        self.assertFalse(exists)

    def test_slice_dpts(self):

        all = ["one", "two", "three", "four", "five", "six", "seven"]

        slice = slice_dpts(all)
        self.assertListEqual(all, slice)

        slice = slice_dpts(all, end="two")
        self.assertListEqual(["one", "two"], slice)

        slice = slice_dpts(all, start="two", end="four")
        self.assertListEqual(["two", "three", "four"], slice)

        # assert raise
        with self.assertRaises(ValueError):
            slice_dpts(all, "two", "1337")

        with self.assertRaises(ValueError):
            slice_dpts(all, "1337", "four")
