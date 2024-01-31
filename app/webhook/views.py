from math import exp
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import requests
import os
import json


@csrf_exempt
def scaleway(request, secret_token):
    if request.method == "POST":
        expected_token = os.environ.get("SCALEWAY_WEBHOOK_TOKEN")
        if expected_token != secret_token:
            # return a 401 error if the token is invalid
            return HttpResponse("Invalid token", status=401)

        mattermost_webhook = os.environ.get("MATTERMOST_RNB_TECH_WEBHOOK_URL")
        payload = json.loads(request.body)
        invoice_start_date = payload["invoice_start_date"]
        threshold = payload["threshold"]

        if (
            mattermost_webhook is None
            or invoice_start_date is None
            or threshold is None
        ):
            return HttpResponse("Bad Request", status=400)

        message = f"Pour la période commençant le {invoice_start_date}, le seuil de consommation de {threshold}% du budget est dépassé."
        # forward the request to the mattermost webhook
        response = requests.post(
            mattermost_webhook,
            json={"text": message},
        )
        # return the response from the mattermost webhook
        return HttpResponse(response)
    else:
        return HttpResponse("This is not a POST request")
