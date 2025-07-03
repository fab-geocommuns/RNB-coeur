import json

from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from django.test import TestCase
from rest_framework.test import APITestCase

from api_alpha.views import summer_challenge_targeted_score
from batid.models import Address
from batid.models import Building
from batid.models import City
from batid.models import Department
from batid.models import Department_subdivided
from batid.models import SummerChallenge


def create_city_dpt(self):
    self.city_1 = City.objects.create(
        name="city_1",
        code_insee="101",
        shape="MULTIPOLYGON (((0 0, 0 1, 1 1, 1 0, 0 0)))",
    )
    self.city_2 = City.objects.create(
        name="city_2",
        code_insee="102",
        shape="MULTIPOLYGON (((1 0, 1 1, 2 1, 2 0, 1 0)))",
    )

    self.dpt_1 = Department.objects.create(
        code="01", name="Ain", shape="MULTIPOLYGON (((0 0, 0 10, 1 10, 1 0, 0 0)))"
    )
    Department_subdivided.objects.create(
        code="01", shape="POLYGON ((0 0, 0 10, 1 10, 1 0, 0 0))"
    )

    self.dpt_2 = Department.objects.create(
        code="02", name="Deux", shape="MULTIPOLYGON (((1 0, 1 10, 2 10, 2 0, 1 0)))"
    )
    Department_subdivided.objects.create(
        code="02", shape="POLYGON ((1 0, 1 10, 2 10, 2 0, 1 0))"
    )


@override_settings(MAX_BUILDING_AREA=float("inf"))
class TestSummerChallenge(TestCase):
    def setUp(self):
        Address.objects.create(id="addr1")
        Address.objects.create(id="addr2")

        create_city_dpt(self)

        self.user = User.objects.create_user(username="user")

        self.building_1 = Building.create_new(
            user=self.user,
            event_origin={"source": "xxx"},
            status="constructed",
            addresses_id=["addr1", "addr2"],
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

    def test_score_address_building_creation(self):
        scores = (
            SummerChallenge.objects.filter(rnb_id=self.building_1.rnb_id)
            .filter(action="set_address")
            .all()
        )
        self.assertEqual(len(scores), 1)
        score = scores[0]
        self.assertEqual(score.user, self.user)
        self.assertEqual(score.rnb_id, self.building_1.rnb_id)
        self.assertEqual(score.score, 3)
        self.assertEqual(score.action, "set_address")
        self.assertEqual(score.city, self.city_1)
        self.assertEqual(score.department, self.dpt_1)
        self.assertEqual(score.event_id, self.building_1.event_id)

    def test_score_building_creation(self):
        scores = (
            SummerChallenge.objects.filter(rnb_id=self.building_1.rnb_id)
            .filter(action="creation")
            .all()
        )
        self.assertEqual(len(scores), 1)
        score = scores[0]
        self.assertEqual(score.user, self.user)
        self.assertEqual(score.rnb_id, self.building_1.rnb_id)
        self.assertEqual(score.score, 2)
        self.assertEqual(score.action, "creation")
        self.assertEqual(score.city, self.city_1)
        self.assertEqual(score.department, self.dpt_1)
        self.assertEqual(score.event_id, self.building_1.event_id)

    def test_score_building_creation_outside_areas(self):
        building = Building.create_new(
            user=self.user,
            event_origin={"source": "xxx"},
            status="constructed",
            addresses_id=["addr1", "addr2"],
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

        scores = (
            SummerChallenge.objects.filter(rnb_id=building.rnb_id)
            .filter(action="creation")
            .all()
        )
        self.assertEqual(len(scores), 1)
        score = scores[0]
        self.assertEqual(score.user, self.user)
        self.assertEqual(score.rnb_id, building.rnb_id)
        self.assertEqual(score.score, 2)
        self.assertEqual(score.action, "creation")
        self.assertIsNone(score.city)
        self.assertIsNone(score.department)
        self.assertEqual(score.event_id, building.event_id)

    def test_score_building_update(self):
        building = Building.create_new(
            user=self.user,
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

        building.update(
            self.user,
            event_origin=None,
            status="demolished",
            addresses_id=["addr1", "addr2"],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [0, 0],
                                [0, 0.10001],
                                [0.1, 0.1],
                                [0.1, 0],
                                [0, 0],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
        )
        building.refresh_from_db()

        scores = (
            SummerChallenge.objects.filter(rnb_id=building.rnb_id)
            .filter(action="set_address")
            .all()
        )
        self.assertEqual(len(scores), 1)
        score = scores[0]
        self.assertEqual(score.user, self.user)
        self.assertEqual(score.rnb_id, building.rnb_id)
        self.assertEqual(score.score, 3)
        self.assertEqual(score.action, "set_address")
        self.assertEqual(score.city, self.city_1)
        self.assertEqual(score.department, self.dpt_1)
        self.assertEqual(score.event_id, building.event_id)

        scores = (
            SummerChallenge.objects.filter(rnb_id=building.rnb_id)
            .filter(action="update_shape")
            .all()
        )
        self.assertEqual(len(scores), 1)
        score = scores[0]
        self.assertEqual(score.user, self.user)
        self.assertEqual(score.rnb_id, building.rnb_id)
        self.assertEqual(score.score, 1)
        self.assertEqual(score.action, "update_shape")
        self.assertEqual(score.city, self.city_1)
        self.assertEqual(score.department, self.dpt_1)
        self.assertEqual(score.event_id, building.event_id)

        scores = (
            SummerChallenge.objects.filter(rnb_id=building.rnb_id)
            .filter(action="update_status")
            .all()
        )
        self.assertEqual(len(scores), 1)
        score = scores[0]
        self.assertEqual(score.user, self.user)
        self.assertEqual(score.rnb_id, building.rnb_id)
        self.assertEqual(score.score, 1)
        self.assertEqual(score.action, "update_status")
        self.assertEqual(score.city, self.city_1)
        self.assertEqual(score.department, self.dpt_1)
        self.assertEqual(score.event_id, building.event_id)

    def test_score_building_deactivate(self):
        building = Building.create_new(
            user=self.user,
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

        building.deactivate(self.user, event_origin=None)
        building.refresh_from_db()

        scores = (
            SummerChallenge.objects.filter(rnb_id=building.rnb_id)
            .filter(action="deactivation")
            .all()
        )
        self.assertEqual(len(scores), 1)
        score = scores[0]
        self.assertEqual(score.user, self.user)
        self.assertEqual(score.rnb_id, building.rnb_id)
        self.assertEqual(score.score, 1)
        self.assertEqual(score.action, "deactivation")
        self.assertEqual(score.city, self.city_1)
        self.assertEqual(score.department, self.dpt_1)
        self.assertEqual(score.event_id, building.event_id)

    def test_score_building_split(self):
        shape = GEOSGeometry(
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
        )

        building = Building.create_new(
            user=self.user,
            event_origin={"source": "xxx"},
            status="constructed",
            addresses_id=[],
            shape=shape,
            ext_ids=[],
        )
        child = {"status": "constructed", "shape": shape, "addresses_cle_interop": []}
        building.split([child, child], self.user, event_origin={"source": "xxx"})
        building.refresh_from_db()

        scores = (
            SummerChallenge.objects.filter(rnb_id=building.rnb_id)
            .filter(action="split")
            .all()
        )
        self.assertEqual(len(scores), 1)
        score = scores[0]
        self.assertEqual(score.user, self.user)
        self.assertEqual(score.rnb_id, building.rnb_id)
        self.assertEqual(score.score, 1)
        self.assertEqual(score.action, "split")
        self.assertEqual(score.city, self.city_1)
        self.assertEqual(score.department, self.dpt_1)
        self.assertEqual(score.event_id, building.event_id)

    def test_score_building_merge(self):
        shape = GEOSGeometry(
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
        )

        building_1 = Building.create_new(
            user=self.user,
            event_origin={"source": "xxx"},
            status="constructed",
            addresses_id=[],
            shape=shape,
            ext_ids=[],
        )
        building_2 = Building.create_new(
            user=self.user,
            event_origin={"source": "xxx"},
            status="constructed",
            addresses_id=[],
            shape=shape,
            ext_ids=[],
        )
        merged_building = Building.merge(
            [building_1, building_2],
            self.user,
            event_origin={"source": "xxx"},
            status="constructed",
            addresses_id=[],
        )

        scores = (
            SummerChallenge.objects.filter(rnb_id=merged_building.rnb_id)
            .filter(action="merge")
            .all()
        )
        self.assertEqual(len(scores), 1)
        score = scores[0]
        self.assertEqual(score.user, self.user)
        self.assertEqual(score.rnb_id, merged_building.rnb_id)
        self.assertEqual(score.score, 1)
        self.assertEqual(score.action, "merge")
        self.assertEqual(score.city, self.city_1)
        self.assertEqual(score.department, self.dpt_1)
        self.assertEqual(score.event_id, merged_building.event_id)


@override_settings(MAX_BUILDING_AREA=float("inf"))
class TestSummerChallengeRanking(APITestCase):
    def test_leaderboard(self):
        user_1 = User.objects.create_user(username="user_1", email="email_1")
        user_2 = User.objects.create_user(username="user_2", email="email_2")
        user_3 = User.objects.create_user(username="user_3", email="email_3")

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
                    ["user_2", 3],
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
        r = self.client.get(f"/api/alpha/editions/ranking/{user_2.id}/")
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
