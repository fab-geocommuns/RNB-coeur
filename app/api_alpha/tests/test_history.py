import json

from django.contrib.auth.models import User
from django.contrib.auth.models import Group

from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from batid.models import Building, Organization, Address
from api_alpha.permissions import RNBContributorPermission


class SimpleHistoryTest(APITestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.rnb_id = None

    def setUp(self):

        # Julie gonna edit the RNB
        user = User.objects.create_user(
            first_name="Julie", last_name="Sigiste", username="ju_sig"
        )

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
        Address.objects.create(id="cle_interop_1")
        Address.objects.create(id="cle_interop_2")

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

    def test_one_history(self):

        # Remove Julie from client credentials
        # The endpoint is public
        self.client.credentials()

        bdg = Building.objects.get(rnb_id=self.rnb_id)
        updated_at = bdg.sys_period.lower

        r = self.client.get(
            f"/api/alpha/buildings/{self.rnb_id}/history/{bdg.event_id}/"
        )
        data = r.json()

        self.assertEqual(r.status_code, 200)

        self.assertDictEqual(
            data,
            {
                "rnb_id": self.rnb_id,
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
                "status": "constructed",
                "ext_ids": [],
                "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
            },
        )

    def test_many_history_rows(self):

        # test rnb_id parameter
        # test event_id parameter
        # test both together
        # verify the order

        pass

    def test_empty_results(self):

        # todo: empty list or 404 ?
        pass
