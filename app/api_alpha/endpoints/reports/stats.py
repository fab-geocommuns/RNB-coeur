from typing import TypedDict

from django.db import connection
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api_alpha.utils.logging_mixin import RNBLoggingMixin
from batid.models import Report


class TagStatsSerializer(serializers.Serializer):
    tag_id = serializers.IntegerField()
    tag_slug = serializers.CharField()
    tag_name = serializers.CharField()
    total_report_count = serializers.IntegerField()
    closed_report_count = serializers.IntegerField()


class ReportStatsSerializer(serializers.Serializer):
    closed_report_count = serializers.IntegerField()
    total_report_count = serializers.IntegerField()
    tag_stats = TagStatsSerializer(many=True)


class TagStats(TypedDict):
    tag_id: int
    tag_slug: str
    tag_name: str
    total_report_count: int
    closed_report_count: int


class ReportStats(TypedDict):
    closed_report_count: int
    total_report_count: int
    tag_stats: list[TagStats]


class ReportStatsView(RNBLoggingMixin, APIView):
    def get(self, request: Request) -> Response:
        overall_closed_report_count = Report.objects.filter(
            status__in=["fixed", "rejected"]
        ).count()
        overall_total_report_count = Report.objects.count()

        per_tag_query = """
            SELECT
                tag.id,
                tag.slug,
                tag.name,
                SUM(CASE WHEN report.status <> 'pending' THEN 1 ELSE 0 END) AS closed_report_count,
                COUNT(report.*) AS total_report_count
            FROM
                batid_report AS report
            JOIN taggit_taggeditem AS tagged_item
                ON tagged_item.object_id = report.id
            JOIN django_content_type
                ON tagged_item.content_type_id = django_content_type.id
            JOIN taggit_tag AS tag
                ON tagged_item.tag_id = tag.id
            WHERE
                django_content_type.app_label = 'batid'
                AND django_content_type.model = 'report'
            GROUP BY
                tag.id,
                tag.slug,
                tag.name
        """

        with connection.cursor() as cursor:
            cursor.execute(per_tag_query)
            rows = cursor.fetchall()

        tag_stats: list[TagStats] = []
        for tag_id, tag_slug, tag_name, closed_report_count, total_report_count in rows:
            tag_stats.append(
                {
                    "tag_id": tag_id,
                    "tag_slug": tag_slug,
                    "tag_name": tag_name,
                    "total_report_count": total_report_count,
                    "closed_report_count": closed_report_count,
                }
            )

        data = {
            "closed_report_count": overall_closed_report_count,
            "total_report_count": overall_total_report_count,
            "tag_stats": tag_stats,
        }

        serializer = ReportStatsSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)
