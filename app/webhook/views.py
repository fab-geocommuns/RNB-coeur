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
        invoice_start_date = request.POST.get('invoice_start_date')
        threshold = request.POST.get('threshold')

        if (
            mattermost_webhook is None
            or invoice_start_date is None
            or threshold is None
        ):
            return HttpResponse("Bad Request", status=400)

        threshold = int(threshold)
        message = f"Attention : notre consommation Scaleway a dépassé {threshold}% du budget attendu pour la période commençant le {invoice_start_date}."
        # forward the request to the mattermost webhook
        response = requests.post(
            mattermost_webhook,
            json={"text": message},
        )
        # return the response from the mattermost webhook
        return HttpResponse(response.content, status=response.status_code)
    else:
        return HttpResponse("This is not a POST request")
