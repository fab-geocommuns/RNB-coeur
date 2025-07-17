import json

from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.utils.timezone import now
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api_alpha.permissions import RNBContributorPermission
from batid.models import Address
from batid.models import Building
from batid.models import BuildingImport
from batid.models import DataFix
from batid.models import Organization


class SingleBuildingHistoryTest(APITestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.rnb_id = None
        self.user_id = None

    def setUp(self):

        # Julie gonna edit the RNB
        user = User.objects.create_user(
            first_name="Julie", last_name="Sigiste", username="ju_sig"
        )
        self.user_id = user.id

        # She is working in this org
        org = Organization.objects.create(name="Mairie de Dreux")
        org.users.set([user])

        # She has the right to edit the RNB
        group = Group.objects.create(name=RNBContributorPermission.group_name)
        user.groups.add(group)

        # She has a token to get authenticated
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + token.key)

        # We need some addresses
        Address.objects.create(
            id="cle_interop_1",
            source="source1",
            street_number="1",
            street="Rue de la Paix",
            city_name="Paris",
            city_zipcode="75001",
            city_insee_code="75056",
        )
        Address.objects.create(
            id="cle_interop_2",
            source="source2",
            street_number="2",
            street_rep="bis",
            street="Rue de la Paix",
            city_name="Paris",
            city_zipcode="75001",
            city_insee_code="75056",
        )

        # She creates a building
        data = {
            "status": "constructed",
            "addresses_cle_interop": ["cle_interop_1", "cle_interop_2"],
            "shape": json.dumps(
                {
                    "coordinates": [
                        [
                            [1.3653609702393794, 48.732855700163356],
                            [1.365308683629877, 48.73273499650409],
                            [1.3657080952289675, 48.73265931707786],
                            [1.3657603818384416, 48.73277523108939],
                            [1.3653609702393794, 48.732855700163356],
                        ]
                    ],
                    "type": "Polygon",
                }
            ),
            "comment": "nouveau bâtiment",
        }
        r = self.client.post(
            f"/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )

        data = r.json()
        self.rnb_id = data["rnb_id"]

    def test_bdg_history(self):

        # The history endpoint is public, we have to check it works without credentials
        # We, remove Julie from client credentials
        self.client.credentials()

        bdg = Building.objects.get(rnb_id=self.rnb_id)

        contrib_id = bdg.event_origin.get("contribution_id", None)
        updated_at = bdg.sys_period.lower

        r = self.client.get(f"/api/alpha/buildings/{self.rnb_id}/history/")
        data = r.json()

        self.maxDiff = None

        self.assertEqual(r.status_code, 200)

        self.assertEqual(len(data), 1)

        self.assertDictEqual(
            data[0],
            {
                "rnb_id": self.rnb_id,
                "is_active": True,
                "shape": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [1.36536097, 48.7328557],
                            [1.365308684, 48.732734997],
                            [1.365708095, 48.732659317],
                            [1.365760382, 48.732775231],
                            [1.36536097, 48.7328557],
                        ]
                    ],
                },
                "addresses": [
                    {
                        "id": "cle_interop_1",
                        "source": "source1",
                        "street_number": "1",
                        "street_rep": None,
                        "street": "Rue de la Paix",
                        "city_name": "Paris",
                        "city_zipcode": "75001",
                        "city_insee_code": "75056",
                    },
                    {
                        "id": "cle_interop_2",
                        "source": "source2",
                        "street_number": "2",
                        "street_rep": "bis",
                        "street": "Rue de la Paix",
                        "city_name": "Paris",
                        "city_zipcode": "75001",
                        "city_insee_code": "75056",
                    },
                ],
                "status": "constructed",
                "event": {
                    "id": str(bdg.event_id),
                    "type": "creation",
                    "details": None,
                    "author": {
                        "id": self.user_id,
                        "first_name": "Julie",
                        "last_name": "S.",
                        "organizations_names": ["Mairie de Dreux"],
                        "username": "ju_sig",
                    },
                    "origin": {
                        "type": "contribution",
                        "details": {
                            "is_report": False,
                            "posted_on": self.rnb_id,
                            "report_text": "nouveau bâtiment",
                            "review_comment": None,
                        },
                        "id": contrib_id,
                    },
                },
                "ext_ids": [],
                "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
            },
        )

    def test_update(self):
        """
        Update specifics to test:
        - the list of updated fields should be available in event.details.updated_fields

        (the updated_fields can contain: status, shape, addresses, ext_ids)
        """

        # We update the building with a new status, a new shape and we remove one address
        data = {
            "status": "demolished",
            "addresses_cle_interop": ["cle_interop_1"],
            "shape": json.dumps(
                {
                    "coordinates": [
                        [
                            [1.3654239303253632, 48.732904411010935],
                            [1.3654239303253632, 48.73278996143884],
                            [1.3658084909711476, 48.73278996143884],
                            [1.3658084909711476, 48.732904411010935],
                            [1.3654239303253632, 48.732904411010935],
                        ]
                    ],
                    "type": "Polygon",
                }
            ),
        }
        self.client.patch(
            f"/api/alpha/buildings/{self.rnb_id}/",
            data=json.dumps(data),
            content_type="application/json",
        )

        # We now verify the history endpoint
        r = self.client.get(f"/api/alpha/buildings/{self.rnb_id}/history/")

        data = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(data), 2)

        # Verify the order of the history (most recent first)
        self.assertEqual(data[0]["event"]["type"], "update")
        self.assertEqual(data[1]["event"]["type"], "creation")

        # Verify the updated_fields
        # NB: we can not change the ext_ids from the API, so it should not be in the updated_fields
        self.assertEqual(
            data[0]["event"]["details"]["updated_fields"],
            ["status", "shape", "addresses"],
        )

        # Spcific assetions for ext_ids
        bdg = Building.objects.get(rnb_id=self.rnb_id)
        new_ext_ids = Building.add_ext_id(
            bdg.ext_ids,
            source="dummy",
            source_version="1.0",
            id="id123",
            created_at=str(now()),
        )
        bdg.update(
            user=None,
            event_origin=None,
            status=None,
            addresses_id=None,
            shape=None,
            ext_ids=new_ext_ids,
        )

        r = self.client.get(f"/api/alpha/buildings/{self.rnb_id}/history/")
        data = r.json()
        self.assertEqual(r.status_code, 200)

        most_recent = data[0]
        self.assertListEqual(
            most_recent["event"]["details"]["updated_fields"], ["ext_ids"]
        )

    def test_merge(self):
        """
        Merge specifics to test:
        - event type is 'merge'
        - event.details contains the merge child and parents' RNB IDs
        """

        # We create a second building
        data = {
            "status": "constructed",
            "addresses_cle_interop": ["cle_interop_1"],
            "shape": json.dumps(
                {
                    "coordinates": [
                        [
                            [1.3653609702393794, 48.732855700163356],
                            [1.365308683629877, 48.73273499650409],
                            [1.3657080952289675, 48.73265931707786],
                            [1.3657603818384416, 48.73277523108939],
                            [1.3653609702393794, 48.732855700163356],
                        ]
                    ],
                    "type": "Polygon",
                }
            ),
            "comment": "nouveau bâtiment qui va être fusionné",
        }
        r = self.client.post(
            f"/api/alpha/buildings/",
            data=json.dumps(data),
            content_type="application/json",
        )
        data = r.json()
        rnb_id2 = data["rnb_id"]

        # We merge the two buildings
        data = {
            "status": "constructed",
            "merge_existing_addresses": True,
            "rnb_ids": [self.rnb_id, rnb_id2],
        }
        r = self.client.post(
            f"/api/alpha/buildings/merge/",
            data=json.dumps(data),
            content_type="application/json",
        )
        data = r.json()
        child_rnb_id = data["rnb_id"]

        self.assertEqual(r.status_code, 201)

        # ###########
        # We are ready to test the history endpoint

        # First we test one of the parents
        r = self.client.get(f"/api/alpha/buildings/{self.rnb_id}/history/")
        data = r.json()
        self.assertEqual(r.status_code, 200)

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["event"]["type"], "merge")
        self.assertEqual(data[0]["event"]["details"]["merge_child"], child_rnb_id)
        self.assertListEqual(
            data[0]["event"]["details"]["merge_parents"],
            [self.rnb_id, rnb_id2],
        )

        # Then, we test the child
        r = self.client.get(f"/api/alpha/buildings/{child_rnb_id}/history/")
        data = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["event"]["type"], "merge")
        self.assertEqual(data[0]["event"]["details"]["merge_child"], child_rnb_id)
        self.assertListEqual(
            data[0]["event"]["details"]["merge_parents"],
            [self.rnb_id, rnb_id2],
        )

    def test_split(self):
        """
        Split specifics to test:
        - event type is 'split'
        - event.details contains the split children and parent's RNB IDs
        """

        # We split the building into two new buildings
        data = {
            "created_buildings": [
                {
                    "status": "constructed",
                    "addresses_cle_interop": [],
                    "shape": json.dumps(
                        {
                            "coordinates": [
                                [
                                    [1.36536097, 48.7328557],
                                    [1.365308684, 48.732734997],
                                    [1.3655, 48.7327],
                                    [1.3655, 48.7328],
                                    [1.36536097, 48.7328557],
                                ]
                            ],
                            "type": "Polygon",
                        }
                    ),
                },
                {
                    "status": "constructed",
                    "addresses_cle_interop": [],
                    "shape": json.dumps(
                        {
                            "coordinates": [
                                [
                                    [1.3655, 48.7327],
                                    [1.365708095, 48.732659317],
                                    [1.365760382, 48.732775231],
                                    [1.3655, 48.7328],
                                    [1.3655, 48.7327],
                                ]
                            ],
                            "type": "Polygon",
                        }
                    ),
                },
            ]
        }
        r = self.client.post(
            f"/api/alpha/buildings/{self.rnb_id}/split/",
            data=json.dumps(data),
            content_type="application/json",
        )
        data = r.json()

        child_rnb_id1 = data[0]["rnb_id"]
        child_rnb_id2 = data[1]["rnb_id"]
        children_rnb_ids = [child_rnb_id1, child_rnb_id2]

        self.assertEqual(r.status_code, 201)

        # ###########
        # We are ready to test the history endpoint

        # First we test the parent
        r = self.client.get(f"/api/alpha/buildings/{self.rnb_id}/history/")
        data = r.json()
        self.assertEqual(r.status_code, 200)

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["event"]["type"], "split")
        self.assertEqual(data[0]["event"]["details"]["split_parent"], self.rnb_id)
        self.assertListEqual(
            sorted(data[0]["event"]["details"]["split_children"]),
            sorted(children_rnb_ids),
        )

        # Then, we test one of the children
        r = self.client.get(f"/api/alpha/buildings/{child_rnb_id1}/history/")
        data = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["event"]["type"], "split")
        self.assertEqual(data[0]["event"]["details"]["split_parent"], self.rnb_id)
        self.assertListEqual(
            sorted(data[0]["event"]["details"]["split_children"]),
            sorted(children_rnb_ids),
        )

    def test_contribution(self):
        """
        Contribution specifics to test:
        - event type is 'contribution'
        - event.details contains is_report (boolean), 'report_text', 'review_comment' and 'posted_on' (rnb_id)
        NB: right now, our edit API does not permit to attach a report to a building version. We always attach a new contribution.
        """

        # The building created in setUp() has a contribution attached to it
        # We do not need to create a new one

        r = self.client.get(f"/api/alpha/buildings/{self.rnb_id}/history/")
        data = r.json()

        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(data), 1)

        # Verify the contribution specifics
        self.assertEqual(data[0]["event"]["origin"]["type"], "contribution")
        self.assertFalse(data[0]["event"]["origin"]["details"]["is_report"])
        self.assertEqual(
            data[0]["event"]["origin"]["details"]["report_text"], "nouveau bâtiment"
        )
        self.assertEqual(
            data[0]["event"]["origin"]["details"]["posted_on"], self.rnb_id
        )
        self.assertIsNone(data[0]["event"]["origin"]["details"]["review_comment"])

    def test_import(self):

        bdg_import = BuildingImport.objects.create(
            import_source="bdtopo",
        )

        bdg = Building.objects.get(rnb_id=self.rnb_id)
        bdg.update(
            event_origin={"source": "import", "id": bdg_import.id},
            user=None,
            status="demolished",
            shape=None,
            addresses_id=None,
            ext_ids=None,
        )

        r = self.client.get(f"/api/alpha/buildings/{self.rnb_id}/history/")
        data = r.json()

        # Verify the import specifics
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["event"]["origin"]["type"], "import")
        self.assertEqual(data[0]["event"]["origin"]["id"], bdg_import.id)
        self.assertEqual(
            data[0]["event"]["origin"]["details"]["imported_database"], "bdtopo"
        )

    def test_data_fix(self):
        """
        Data fix specifics to test:
        - event type is 'data_fix'
        """
        df = DataFix.objects.create(text="Test data fix")

        bdg = Building.objects.get(rnb_id=self.rnb_id)
        bdg.update(
            event_origin={"source": "data_fix", "id": df.id},
            user=None,
            status="demolished",
            shape=None,
            addresses_id=None,
            ext_ids=None,
        )

        r = self.client.get(f"/api/alpha/buildings/{self.rnb_id}/history/")
        data = r.json()
        self.assertEqual(r.status_code, 200)

        # Verify the data fix specifics
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["event"]["origin"]["type"], "data_fix")
        self.assertEqual(data[0]["event"]["origin"]["id"], df.id)
        self.assertEqual(
            data[0]["event"]["origin"]["details"]["description"], "Test data fix"
        )

    def test_unknwon_rnb_id(self):
        """
        Test that the history endpoint returns a 404 when the RNB ID does not exist
        """
        r = self.client.get(f"/api/alpha/buildings/1234ABCD1234/history/")
        self.assertEqual(r.status_code, 404)
