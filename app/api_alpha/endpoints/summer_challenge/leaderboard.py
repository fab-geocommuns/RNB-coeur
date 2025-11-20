from django.http import JsonResponse
from rest_framework.request import Request
from rest_framework.views import APIView

from api_alpha.endpoints.summer_challenge.common import summer_challenge_leaderboard


class LeaderboardView(APIView):
    def get(self, request: Request) -> JsonResponse:
        max_rank = int(request.GET.get("max_rank", 5))
        leaderboard = summer_challenge_leaderboard(max_rank)
        return JsonResponse(leaderboard)
