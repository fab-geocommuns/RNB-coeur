import json
import os

from batid.services.tchap import TchapLevel, notify_tech
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def scaleway(request, secret_token):
    """
    Receive Scaleway budget alerts and forward them to the tech team Tchap room.
    """
    if request.method == "POST":
        expected_token = os.environ.get("SCALEWAY_WEBHOOK_TOKEN")
        if expected_token != secret_token:
            # return a 401 error if the token is invalid
            return HttpResponse("Invalid token", status=401)

        json_data = json.loads(request.body)
        invoice_start_date = json_data.get("invoice_start_date")
        threshold = json_data.get("threshold")

        if invoice_start_date is None or threshold is None:
            return HttpResponse("Bad Request", status=400)

        threshold = int(threshold)
        notify_tech(
            level=TchapLevel.ALERT,
            title="Alerte budget Scaleway",
            details=[
                ("Seuil", f"{threshold} %"),
                ("Période", f"à partir du {invoice_start_date}"),
            ],
        )

        return HttpResponse("ok", status=200)
    else:
        return HttpResponse("This is not a POST request")
