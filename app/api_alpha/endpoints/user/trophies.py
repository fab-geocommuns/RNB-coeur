from batid.models import Trophy
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class UserTrophiesView(APIView):
    def get(self, request: Request, username: str) -> Response:
        # check the user exists
        user = get_object_or_404(User, username=username)

        trophies = (
            Trophy.objects.filter(user=user)
            .order_by("-level_unlocked_at")
            .values("trophy_type", "level", "level_unlocked_at")
        )

        data = [
            {
                "trophy": t["trophy_type"],
                "trophy_label": Trophy.trophy_label(t["trophy_type"]),
                "level": t["level"],
                "level_label": Trophy.level_label(t["trophy_type"], t["level"]),
                "unlocked_at": t["level_unlocked_at"],
            }
            for t in trophies
        ]
        return Response(data)
