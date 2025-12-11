from django.db import connection
from batid.models import SummerChallenge
from django.db.models import Count


def summer_challenge_global_score():
    global_score = SummerChallenge.objects.aggregate(
        score=Count("event_id", distinct=True)
    )
    return global_score["score"]


def summer_challenge_leaderboard(max_rank):
    global_score = summer_challenge_global_score()

    individual_ranking = (
        SummerChallenge.objects.values_list("user__username")
        .annotate(score=Count("event_id", distinct=True))
        .order_by("-score")[:max_rank]
    )
    individual_ranking = [list(row) for row in individual_ranking]

    city_ranking = (
        SummerChallenge.objects.exclude(city__isnull=True)
        .values_list("city__code_insee", "city__name")
        .annotate(score=Count("event_id", distinct=True))
        .order_by("-score")[:max_rank]
    )
    city_ranking = [list(row) for row in city_ranking]

    departement = (
        SummerChallenge.objects.exclude(department__isnull=True)
        .values_list("department__code", "department__name")
        .annotate(score=Count("event_id", distinct=True))
        .order_by("-score")[:max_rank]
    )
    departement_ranking = [list(row) for row in departement]

    return {
        "global": global_score,
        "individual": individual_ranking,
        "city": city_ranking,
        "departement": departement_ranking,
    }
