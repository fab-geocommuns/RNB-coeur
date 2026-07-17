from api_alpha.endpoints.summer_challenge.common import validation_ranking
from django.http import JsonResponse
from rest_framework.request import Request
from rest_framework.views import APIView


class ValidationRankingView(APIView):
    def get(self, request: Request) -> JsonResponse:
        max_rank = int(request.GET.get("max_rank", 5))
        ranking = validation_ranking(max_rank)
        return JsonResponse(ranking)
