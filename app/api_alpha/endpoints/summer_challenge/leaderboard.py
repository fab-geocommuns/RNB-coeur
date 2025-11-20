from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from api_alpha.endpoints.summer_challenge.common import summer_challenge_leaderboard
from django.http import JsonResponse


class LeaderboardView(APIView):
    def get(self, request: Request) -> Response:
        max_rank = int(request.GET.get("max_rank", 5))
        leaderboard = summer_challenge_leaderboard(max_rank)
        return JsonResponse(leaderboard)
