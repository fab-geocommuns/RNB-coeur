from django.test import TestCase

from batid.services.administrative_areas import com_list
from batid.services.administrative_areas import dpt_list_metropole
from batid.services.administrative_areas import dpt_list_overseas
from batid.services.administrative_areas import dpt_name
from batid.services.administrative_areas import dpts_list


class AdminAreas(TestCase):
    def test(self):

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
