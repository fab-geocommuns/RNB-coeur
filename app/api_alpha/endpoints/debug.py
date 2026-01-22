from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from batid.services.mattermost import notify_if_error


class RaiseExceptionView(APIView):
    permission_classes = [AllowAny]

    @notify_if_error
    def get(self, request):
        raise Exception(
            "This is a test exception raised by the /api/alpha/raise_exception endpoint."
        )
