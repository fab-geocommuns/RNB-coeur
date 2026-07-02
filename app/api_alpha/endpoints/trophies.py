from batid.models import Trophy
from django.db.models import Count
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class TrophiesView(APIView):
    """List every trophy that can be earned, with the number of distinct users who
    earned it (all levels combined) and the breakdown per level."""

    def get(self, request: Request) -> Response:
        # distinct user counts, in two grouped queries (per trophy_type and per level)
        trophy_counts = {
            row["trophy_type"]: row["count"]
            for row in Trophy.objects.values("trophy_type").annotate(
                count=Count("user", distinct=True)
            )
        }
        level_counts = {
            (row["trophy_type"], row["level"]): row["count"]
            for row in Trophy.objects.values("trophy_type", "level").annotate(
                count=Count("user", distinct=True)
            )
        }

        data = [
            {
                "trophy": t.trophy_type,
                "trophy_label": t.label,
                "description": t.description,
                "count": trophy_counts.get(t.trophy_type, 0),
                "levels": [
                    {
                        "level": lvl.level,
                        "level_label": lvl.label,
                        "condition": lvl.condition,
                        "count": level_counts.get((t.trophy_type, lvl.level), 0),
                    }
                    for lvl in t.levels
                ],
            }
            for t in Trophy.TROPHY_DEFS
        ]
        return Response(data)
