from rest_framework.test import APITestCase

from batid.models import Building
from batid.models import Contribution


class TestContribution(APITestCase):
    def test_create_contribution(self):
        """"""

        # Create a building
        Building.objects.create(rnb_id="111")

        # Post a contribution about it
        r = self.client.post(
            "/api/alpha/contributions/", data={"rnb_id": "111", "text": "I exist"}
        )
        self.assertEqual(r.status_code, 201)

        contrib = Contribution.objects.first()
        self.assertEqual(Contribution.objects.count(), 1)
        self.assertEqual(contrib.text, "I exist")
        self.assertEqual(contrib.rnb_id, "111")
        self.assertEqual(contrib.status, "pending")

    def test_create_inactive_bdg(self):
        """
        It should not be possible to post a new contribution about an inactive building
        :return:
        """

        # The inactive building
        Building.objects.create(rnb_id="AAA", is_active=False)

        # Post a contribution about it
        r = self.client.post(
            "/api/alpha/contributions/",
            data={"rnb_id": "AAA", "text": "I shoud not exist"},
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json(), {"rnb_id": ['Building "AAA" is not active.']})
