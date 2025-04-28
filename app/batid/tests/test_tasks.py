from unittest import mock

from django.test import TestCase
from django.conf import settings

from batid.tasks import create_sandbox_user

import json


class TestCreateSandboxUserTask(TestCase):
    @mock.patch("batid.tasks.make_random_password")
    @mock.patch("requests.request")
    def test_create_sandbox_user_task(self, mock_request, mock_make_password):
        with self.settings(
            SANDBOX_URL="https://sandbox.example.test",
        ):
            user_data = {
                "last_name": "B",
                "first_name": "Julie",
                "email": "julie.b@exemple.com",
                "username": "juju",
                "organization_name": "Mairie d'Angoulème",
                "job_title": "responsable SIG",
            }

            mock_make_password.return_value = "randomly_generated_password"
            mock_request.return_value = mock.Mock(status_code=200)

            create_sandbox_user(user_data)

            mock_make_password.assert_called_once_with(length=24)

            call_args = mock_request.call_args
            self.assertEqual(call_args[0][0], "POST")
            self.assertEqual(
                call_args[0][1], "https://sandbox.example.test/api/alpha/auth/users/"
            )
            expected_json_params = {
                **user_data,
                "password": "randomly_generated_password",
            }
            self.assertEqual(
                json.dumps(call_args[1]["json"]), json.dumps(expected_json_params)
            )
