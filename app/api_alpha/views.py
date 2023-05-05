from api_alpha.permissions import ADSPermission
from api_alpha.serializers import ADSSerializer, BuildingSerializer, CitySerializer
from batid.logic.ads_search import ADSSearch
from batid.logic.bdg_search import BuildingSearch
from batid.models import ADS, Building, BuildingADS, City
from django.db.models import Q, Case, When, Value, FloatField, F

from rest_framework import viewsets
from rest_framework.exceptions import ParseError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet


class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
    http_method_names = ["get"]
    pagination_class = PageNumberPagination
    lookup_field = "rnb_id"

    def get_queryset(self):
        search = BuildingSearch(**self.request.query_params.dict())

        if not search.is_valid():
            raise ParseError({"errors": search.errors})
            return

        return search.get_queryset()


class CityViewSet(ReadOnlyModelViewSet):
    """View to look up city matching (name or postal code) with a given input"""

    queryset = City.objects.all()
    lookup_field = "code_insee"

    def get_queryset(self):
        query = self.request.query_params.dict()

        qs = City.objects.all()

        if query.get("q"):
            qs = (
                qs.filter(
                    Q(name__unaccent__icontains=query["q"])
                    | Q(code_insee__icontains=query["q"])
                )
                .annotate(
                    start=Case(
                        When(name__unaccent__istartswith=query["q"], then=Value(1)),
                        default=Value(0),
                        output_field=FloatField(),
                    ),
                    equal=Case(
                        When(name__unaccent__iexact=query["q"], then=Value(1)),
                        default=Value(0),
                        output_field=FloatField(),
                    ),
                    rank=F("start"),
                )
                .order_by("-rank", "name")
            )

        return qs

    def retrieve(self, request, code_insee=None):
        return super().retrieve(request, code_insee)

    serializer_class = CitySerializer
    http_method_names = ["get"]
    # pagination_class = PageNumberPagination


class ADSViewSet(viewsets.ModelViewSet):
    queryset = ADS.objects.all()
    serializer_class = ADSSerializer
    lookup_field = "issue_number"
    pagination_class = PageNumberPagination
    permission_classes = [ADSPermission]
    http_method_names = ["get", "post", "put", "delete"]

    def get_queryset(self):
        search = ADSSearch(**self.request.query_params.dict())

        if not search.is_valid():
            raise ParseError({"errors": search.errors})
            pass

        return search.get_queryset()

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=400)

    def retrieve(self, request, issue_number=None):
        return super().retrieve(request, issue_number)
