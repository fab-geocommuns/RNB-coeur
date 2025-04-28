import requests
from django.conf import settings


class SandboxClientError(Exception):
    pass


class SandboxClient:
    def __init__(self):
        self.base_url = settings.SANDBOX_URL

    def create_user(self, user_data: dict) -> None:
        self._request("POST", "auth/users/", json=user_data)
        return None

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/api/alpha/{path}"
        print("Sandbox client request: ", method, url)
        response = requests.request(
            method,
            url,
            **kwargs,
        )
        if response.status_code != 200 and response.status_code != 201:
            raise SandboxClientError(
                f"Failed to {method} {url}: {response.status_code}"
            )
        return response
