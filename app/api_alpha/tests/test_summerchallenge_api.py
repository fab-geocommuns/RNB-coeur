import json
import uuid
from urllib.parse import quote

from batid.models import Address, Building, Organization, SummerChallenge, UserProfile
from batid.tests.factories.users import ContributorUserFactory
from batid.tests.test_summerchallenge import create_city_dpt
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from rest_framework.test import APITestCase


@override_settings(MAX_BUILDING_AREA=float("inf"))
class TestSummerChallengeRanking(APITestCase):
    def test_leaderboard(self):
        user_1 = ContributorUserFactory(username="user_1", email="email_1")
        user_2 = ContributorUserFactory(
            username="user_2@email.com", email="email_2@rnb.fr"
        )
        user_3 = ContributorUserFactory(username="user_3", email="email_3")
        user_4 = ContributorUserFactory(username="user_4", email="email_4")

        Address.objects.create(id="addr1")
        Address.objects.create(id="addr2")

        create_city_dpt(self)

        # user_1 creates a building
        building_1 = Building.create_new(
            user=user_1,
            event_origin={"source": "xxx"},
            status="constructed",
            addresses_id=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [0, 0],
                                [0, 0.1],
                                [0.1, 0.1],
                                [0.1, 0],
                                [0, 0],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
            ext_ids=[],
        )

        # user_2 udpates the building with addresses
        building_1.update(
            user_2,
            event_origin=None,
            status=None,
            addresses_id=["addr1", "addr2"],
            shape=None,
        )

        # user_1 creates a building not in city nor dpt
        building_2 = Building.create_new(
            user=user_1,
            event_origin={"source": "xxx"},
            status="constructed",
            addresses_id=[],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [20, 20],
                                [20, 20.1],
                                [20.1, 20.1],
                                [20.1, 20],
                                [20, 20],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
            ext_ids=[],
        )

        # user_3 updates the status
        building_2.update(
            user_3,
            event_origin=None,
            status="demolished",
            addresses_id=None,
            shape=None,
        )

        r = self.client.get("/api/alpha/editions/ranking/?max_rank=5")
        leaderboard = r.json()
        self.assertDictEqual(
            leaderboard,
            {
                "global": 4,  # 2 creations, 1 address update, 1 status update
                "individual": [
                    ["user_1", 2],
                    ["user_2@email.com", 1],
                    ["user_3", 1],
                ],  # user_1 : 2 creations, user_2 : address update, user_3 : status update
                "city": [["101", "city_1", 2]],  # creation + address update in city
                "departement": [
                    ["01", "Ain", 2]
                ],  # creation + address update in department
            },
        )

        r = self.client.get("/api/alpha/editions/ranking/?max_rank=1")
        leaderboard = r.json()
        self.assertDictEqual(
            leaderboard,
            {
                "global": 4,
                "individual": [["user_1", 2]],
                "city": [["101", "city_1", 2]],
                "departement": [["01", "Ain", 2]],
            },
        )

        # individual ranking of user_2
        r = self.client.get(f"/api/alpha/editions/ranking/{user_2.username}/")
        score = r.json()
        self.assertDictEqual(
            score,
            {
                "global": 4,
                "user_score": 1,
                "user_rank": 2,
            },
        )

        # check the url accepts the email
        encoded_email = quote(user_2.email)

        r = self.client.get(f"/api/alpha/editions/ranking/{encoded_email}/")
        self.assertEqual(r.status_code, 200)

        # individual ranking of non existing user
        r = self.client.get(f"/api/alpha/editions/ranking/coucou/")
        self.assertEqual(r.status_code, 404)

        # check user 4 has a score of 0 and not in the ranking
        r = self.client.get(f"/api/alpha/editions/ranking/{user_4.username}/")
        score = r.json()
        self.assertDictEqual(
            score,
            {
                "global": 4,
                "user_score": 0,
                "user_rank": None,
            },
        )

    def test_validation_ranking(self):
        """
        Input: 6 validation SummerChallenge rows spread over 3 users belonging
        to 2 organizations and located in 2 departments, plus 1 non-validation
        row (a creation) that must be ignored.
            - user_1 (org_a, dpt 01): 3 validations
            - user_2 (org_a, dpt 02): 2 validations
            - user_3 (no org, no dpt): 1 validation
            - user_3: 1 creation (ignored)
        Expected: global=6 and rankings (capped by max_rank) by user,
        department and organization, ordered by descending score. The
        organization ranking only counts users having an organization, and the
        department ranking only counts rows with a department.
        """
        org_a = Organization.objects.create(name="org_a")
        org_b = Organization.objects.create(name="org_b")

        user_1 = ContributorUserFactory(username="user_1")
        user_2 = ContributorUserFactory(username="user_2")
        user_3 = ContributorUserFactory(username="user_3")

        UserProfile.objects.filter(user=user_1).update(organization=org_a)
        UserProfile.objects.filter(user=user_2).update(organization=org_b)
        # user_3 has no organization

        create_city_dpt(self)

        def add_validations(user, n, department=None):
            for _ in range(n):
                SummerChallenge.objects.create(
                    user=user,
                    action="validation",
                    rnb_id="RNBTESTID000",
                    event_id=uuid.uuid4(),
                    department=department,
                )

        add_validations(user_1, 3, department=self.dpt_1)  # org_a, dpt 01
        add_validations(user_2, 2, department=self.dpt_2)  # org_b, dpt 02
        add_validations(user_3, 1)  # no org, no department

        # a non-validation row that must not be counted
        SummerChallenge.objects.create(
            user=user_3,
            action="creation",
            rnb_id="RNBTESTID000",
            event_id=uuid.uuid4(),
        )

        r = self.client.get("/api/alpha/validation/ranking/?max_rank=5")
        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(
            r.json(),
            {
                "global": 6,
                "individual": [["user_1", 3], ["user_2", 2], ["user_3", 1]],
                "departement": [["01", "Ain", 3], ["02", "Deux", 2]],
                "organization": [["org_a", 3], ["org_b", 2]],
            },
        )

        # max_rank caps the length of every ranking
        r = self.client.get("/api/alpha/validation/ranking/?max_rank=1")
        self.assertDictEqual(
            r.json(),
            {
                "global": 6,
                "individual": [["user_1", 3]],
                "departement": [["01", "Ain", 3]],
                "organization": [["org_a", 3]],
            },
        )
