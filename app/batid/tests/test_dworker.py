from django.test import TestCase
from batid.tasks import test_all


class TestDworker(TestCase):
    def test_test_all(self):
        self.assertEqual(test_all(), "done")
