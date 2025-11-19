import json
from urllib.parse import quote

from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from rest_framework.test import APITestCase

from api_alpha.views import summer_challenge_targeted_score
from batid.models import Address
from batid.models import Building
from batid.tests.test_summerchallenge import create_city_dpt
from batid.tests.factories.users import ContributorUserFactory


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
                "goal": summer_challenge_targeted_score(),
                "global": 8,  # 2 creations, 1 address update, 1 status update
                "individual": [
                    ["user_1", 4],
                    ["user_2@email.com", 3],
                    ["user_3", 1],
                ],  # user_1 : 2 creations, user_2 : address update, user_3 : status update
                "city": [["101", "city_1", 5]],  # creation + address update in city
                "departement": [
                    ["01", "Ain", 5]
                ],  # creation + address update in department
            },
        )

        r = self.client.get("/api/alpha/editions/ranking/?max_rank=1")
        leaderboard = r.json()
        self.assertDictEqual(
            leaderboard,
            {
                "goal": summer_challenge_targeted_score(),
                "global": 8,
                "individual": [["user_1", 4]],
                "city": [["101", "city_1", 5]],
                "departement": [["01", "Ain", 5]],
            },
        )

        # individual ranking of user_2
        r = self.client.get(f"/api/alpha/editions/ranking/{user_2.username}/")
        score = r.json()
        self.assertDictEqual(
            score,
            {
                "goal": summer_challenge_targeted_score(),
                "global": 8,
                "user_score": 3,
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
                "goal": summer_challenge_targeted_score(),
                "global": 8,
                "user_score": 0,
                "user_rank": None,
            },
        )
