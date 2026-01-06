from django.db.models import F
from django.http import JsonResponse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.endpoints.summer_challenge.common import summer_challenge_leaderboard
from batid.models.feve import Feve


class LeaderboardView(APIView):
    def get(self, request: Request) -> JsonResponse:
        max_rank = int(request.GET.get("max_rank", 5))
        leaderboard = summer_challenge_leaderboard(max_rank)
        return JsonResponse(leaderboard)


class FevesView(APIView):
    def get(self, request: Request) -> JsonResponse:
        qs = (
            Feve.objects.select_related("department", "found_by")
            .values(
                department_code=F("department__code"),
                department_name=F("department__name"),
                found_by_username=F("found_by__username"),
                found_datetime=F("found_at"),
            )
            .order_by("department__code")
        )

        return Response(list(qs))
