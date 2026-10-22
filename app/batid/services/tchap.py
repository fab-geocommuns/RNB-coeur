import os
import uuid
from urllib.parse import quote

import requests
from django.conf import settings


def notify_tech(msg: str) -> None:
    """
    Send a text message to the tech team Tchap room.

    Tchap is a Matrix server, so we use the Matrix client API directly:
    https://spec.matrix.org/latest/client-server-api/#put_matrixclientv3roomsroomidsendeventtypetxnid

    Configuration (environment variables):
    - TCHAP_HOMESERVER_URL: Matrix homeserver base URL, e.g. https://matrix.agent.dinum.tchap.gouv.fr
    - TCHAP_ACCESS_TOKEN: access token of the bot account
    - TCHAP_ROOM_ID: internal room id, e.g. !abc123:agent.dinum.tchap.gouv.fr
      The room must be unencrypted: this bot does not support end-to-end encryption.

    About the access token: it is obtained once with a password login on the bot
    account (POST /_matrix/client/v3/login) and it is tied to that login session.
    Logging out of that session (from the Tchap UI or by deleting the device in the
    account security settings) revokes the token. If the API answers with the
    M_UNKNOWN_TOKEN error code, a new login is needed and the environment variable
    must be updated. Do not log in on every call: this would create one session per
    notification and Tchap asks bots to keep a single session.
    """

    if not _notifications_are_active():
        return

    homeserver_url = os.environ.get("TCHAP_HOMESERVER_URL")
    access_token = os.environ.get("TCHAP_ACCESS_TOKEN")
    room_id = os.environ.get("TCHAP_ROOM_ID")

    if not homeserver_url or not access_token or not room_id:
        raise Exception(
            "Tchap notifications are active but TCHAP_HOMESERVER_URL, TCHAP_ACCESS_TOKEN or TCHAP_ROOM_ID is missing"
        )

    # The transaction id makes the request idempotent on the Matrix side.
    # It must be unique per message for a given access token.
    txn_id = uuid.uuid4()
    url = f"{homeserver_url.rstrip('/')}/_matrix/client/v3/rooms/{quote(room_id, safe='')}/send/m.room.message/{txn_id}"

    r = requests.put(
        url,
        json={"msgtype": "m.text", "body": msg},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )

    if r.status_code != 200:
        raise Exception(
            f"Error {r.status_code} while sending the Tchap notification: {r.text}"
        )


# create a decorator to notify the tech team
def notify_if_error(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            notify_tech(f"Error while executing {func.__name__}: {e}")
            raise e

    return wrapper


def _notifications_are_active() -> bool:
    return settings.TCHAP_NOTIFICATIONS
