from django.contrib.auth.models import User
from django.db.models import Count
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework.request import Request
from rest_framework.views import APIView

from api_alpha.endpoints.summer_challenge.common import summer_challenge_global_score
from batid.models import SummerChallenge


class UserScoreView(APIView):
    def get(self, request: Request, username: str) -> JsonResponse:
        # Check the user exists, we look by username or email
        get_object_or_404(User, Q(username=username) | Q(email=username))

        global_score = summer_challenge_global_score()
        individual_ranking = (
            SummerChallenge.objects.values("user__username", "user__email")
            .annotate(score=Count("event_id", distinct=True))
            .order_by("-score")
        )

        user_score = 0
        user_rank = None

        for i, rank in enumerate(individual_ranking):
            if rank["user__username"] == username or rank["user__email"] == username:
                user_score = rank["score"]
                user_rank = i + 1
                break

        data = {
            "global": global_score,
            "user_score": user_score,
            "user_rank": user_rank,
        }
        return JsonResponse(data)
