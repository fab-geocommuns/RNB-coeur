from django.test import TestCase

from batid.services.administrative_areas import (
    dpt_list_metropole,
    dpt_list_overseas,
    com_list,
    dpts_list,
    dpt_name,
)


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
