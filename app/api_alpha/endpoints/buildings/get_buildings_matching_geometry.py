from django.contrib.gis.geos import GEOSGeometry
from django.db.models.expressions import RawSQL
from rest_framework import status as http_status
from rest_framework.request import Request

from batid.utils.geo import assert_shape_is_valid
from batid.list_bdg import list_bdgs
from django.db.models import (
    ExpressionWrapper,
    FloatField,
    Func,
)

from api_alpha.utils.logging_mixin import RNBLoggingMixin
from rest_framework.response import Response
from rest_framework.views import APIView
from api_alpha.serializers.serializers import BuildingsMatchingGeometryQuerySerializer
from rest_framework.permissions import AllowAny
from api_alpha.pagination import BuildingListingCursorPagination
from api_alpha.serializers.serializers import BuildingSerializer

class BuildingsMatchingGeometryView(RNBLoggingMixin, APIView):
    
    # @TODO: add documentation
    # @TODO: add tests
    # @TODO: set up permissions ?? permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        data_serializer = BuildingsMatchingGeometryQuerySerializer(data=request.data)
        data_serializer.is_valid(raise_exception=True)
        geom = GEOSGeometry(data_serializer.data.get("geom"), srid=4326)
        isValidGeom = assert_shape_is_valid(geom)
        if not isValidGeom:
            return Response({"error": "Invalid geometry"}, status=http_status.HTTP_400_BAD_REQUEST)
        buildings = list_bdgs(data_serializer.data, only_active=True)
        iou_annotation = ExpressionWrapper(
            Func(
                Func("shape", RawSQL("ST_GeomFromText(%s, 4326)", [geom.wkt]), function="ST_Intersection"),
                function="ST_Area",
                output_field=FloatField(),
            ) / Func(
                Func("shape", RawSQL("ST_GeomFromText(%s, 4326)", [geom.wkt]), function="ST_Union"),
                function="ST_Area",
                output_field=FloatField(),
            ),
            output_field=FloatField(),
        )
        buildings = buildings.annotate(iou=iou_annotation).order_by("iou")
        paginator = BuildingListingCursorPagination()
        paginated_buildings = paginator.paginate_queryset(buildings, request)
        serializer = BuildingSerializer(paginated_buildings, with_plots=False, many=True)
        return paginator.get_paginated_response(serializer.data)