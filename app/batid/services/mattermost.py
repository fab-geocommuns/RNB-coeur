import json
import os

import requests


def notify_tech(msg):

    MATTERMOST_RNB_TECH_WEBHOOK_URL = os.environ.get("MATTERMOST_RNB_TECH_WEBHOOK_URL")

    data = {
        "username": "backup-bot",
        "text": msg,
    }

    r = requests.post(MATTERMOST_RNB_TECH_WEBHOOK_URL, data=json.dumps(data))

    if r.status_code != 200:
        raise Exception(
            f"Error {r.status_code} while sending the mattermost notification"
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
