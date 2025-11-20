from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from api_alpha.endpoints.summer_challenge.common import summer_challenge_global_score
from api_alpha.endpoints.summer_challenge.common import summer_challenge_targeted_score
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework.exceptions import NotFound
from batid.models import SummerChallenge
from django.db.models import Count


class UserScoreView(APIView):
    def get(self, request: Request, username: str) -> JsonResponse:
        # Check the user exists, we look by username or email
        try:
            User.objects.get(
                Q(username=username) | Q(email=username)
            )  # This will raise an exception if the user does not exist
        except User.DoesNotExist:
            raise NotFound()

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
            "goal": summer_challenge_targeted_score(),
            "global": global_score,
            "user_score": user_score,
            "user_rank": user_rank,
        }
        return JsonResponse(data)
