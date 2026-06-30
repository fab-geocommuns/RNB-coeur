from batid.models import Trophy
from django.db.models import Count
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class TrophiesView(APIView):
    """List every trophy that can be earned, with the number of distinct users who
    earned it (all levels combined) and the breakdown per level."""

    def get(self, request: Request) -> Response:
        # distinct user counts, in two grouped queries (per label and per level)
        trophy_counts = {
            row["label"]: row["count"]
            for row in Trophy.objects.values("label").annotate(
                count=Count("user", distinct=True)
            )
        }
        level_counts = {
            (row["label"], row["level"]): row["count"]
            for row in Trophy.objects.values("label", "level").annotate(
                count=Count("user", distinct=True)
            )
        }

        data = [
            {
                "trophy": label,
                "trophy_label": Trophy.trophy_label(label),
                "description": Trophy.trophy_description(label),
                "count": trophy_counts.get(label, 0),
                "levels": [
                    {
                        "level": level,
                        "level_label": Trophy.level_label(label, level),
                        "condition": Trophy.level_condition(label, level),
                        "count": level_counts.get((label, level), 0),
                    }
                    for level in Trophy.levels(label)
                ],
            }
            for label in Trophy.TROPHY_LABELS
        ]
        return Response(data)
