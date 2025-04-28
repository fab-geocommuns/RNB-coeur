import requests
from django.conf import settings
import base64


class SandboxClientError(Exception):
    pass


class SandboxClient:
    def __init__(self):
        self.base_url = settings.SANDBOX_URL
        self.secret_token = settings.SANDBOX_SECRET_TOKEN

    def get_user_token(self, user_email: str) -> str:
        base_64_user_email = base64.b64encode(user_email.encode("utf-8")).decode(
            "utf-8"
        )
        response = self._request("GET", f"auth/users/{base_64_user_email}/token")
        return response.json()["token"]

    def create_user(self, user_data: dict) -> None:
        self._request("POST", "auth/users/", json=user_data)
        return None

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/api/alpha/{path}"
        print("Sandbox client request: ", method, url)
        response = requests.request(
            method,
            url,
            headers={"Authorization": f"Bearer {self.secret_token}"},
            **kwargs,
        )
        if response.status_code != 200 and response.status_code != 201:
            raise SandboxClientError(
                f"Failed to {method} {url}: {response.status_code}"
            )
        return response
