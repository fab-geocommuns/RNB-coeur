import base64
import secrets

import requests
from django.conf import settings


class SandboxClientError(Exception):
    """Raised when the sandbox API answers with an unexpected status.

    Carries the status code and body so callers can tell apart a duplicate
    account (400), a throttled call (429) and a genuine failure.
    """

    def __init__(self, message: str, status_code: int | None = None, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def has_sandbox_secret(request) -> bool:
    """True when the request carries the shared production -> sandbox secret.

    Identifies trusted server-to-server calls coming from the production
    instance, as opposed to ordinary public traffic.
    """
    expected = settings.SANDBOX_SECRET_TOKEN
    if not expected:
        return False
    provided = request.headers.get("Authorization") or ""
    return secrets.compare_digest(
        provided.encode("utf-8", "replace"),
        f"Bearer {expected}".encode("utf-8", "replace"),
    )


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
        url = f"{self.base_url.rstrip('/')}/api/alpha/{path}"
        print("Sandbox client request: ", method, url)
        response = requests.request(
            method,
            url,
            headers={"Authorization": f"Bearer {self.secret_token}"},
            **kwargs,
        )
        if response.status_code != 200 and response.status_code != 201:
            raise SandboxClientError(
                f"Failed to {method} {url}: {response.status_code}",
                status_code=response.status_code,
                body=response.text[:500],
            )
        return response
