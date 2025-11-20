from django.contrib.gis.geos import Point
from rest_framework.test import APITestCase

from batid.models import Report


class ReportStatsTest(APITestCase):
    def test_stats_empty(self):
        response = self.client.get("/api/alpha/reports/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "closed_report_count": 0,
                "total_report_count": 0,
                "tag_stats": [],
            },
        )

    def test_stats_comprehensive(self):
        point = Point(2.3522, 48.8566, srid=4326)
        """
        Comprehensive test with 2 tags and 5 reports:
        - 1 report without tag (pending)
        - 1 report with a single tag (Tag1, pending)
        - 1 report with 2 tags (Tag1 + Tag2, pending)
        - 1 report with 2 tags (Tag1 + Tag2, fixed)
        - 1 report with 2 tags (Tag1 + Tag2, rejected)
        """
        # Report 1: No tags, pending
        report1 = Report.objects.create(
            point=point,
            status="pending",
        )

        # Report 2: Single tag (Tag1), pending
        report2 = Report.objects.create(
            point=point,
            status="pending",
        )
        report2.tags.set(["Tag1"])

        # Report 3: Two tags (Tag1 + Tag2), pending
        report3 = Report.objects.create(
            point=point,
            status="pending",
        )
        report3.tags.set(["Tag1", "Tag2"])

        # Report 4: Two tags (Tag1 + Tag2), fixed
        report4 = Report.objects.create(
            point=point,
            status="fixed",
        )
        report4.tags.set(["Tag1", "Tag2"])

        # Report 5: Two tags (Tag1 + Tag2), rejected
        report5 = Report.objects.create(
            point=point,
            status="rejected",
        )
        report5.tags.set(["Tag1", "Tag2"])

        response = self.client.get("/api/alpha/reports/stats/")
        self.assertEqual(response.status_code, 200)

        data = response.json()

        # Check overall stats
        self.assertEqual(data["total_report_count"], 5)
        self.assertEqual(data["closed_report_count"], 2)  # fixed + rejected

        # Check tag stats
        tag_stats = data["tag_stats"]
        self.assertEqual(len(tag_stats), 2)

        tag1_stats = tag_stats[0]
        self.assertEqual(tag1_stats["tag_name"], "Tag1")
        self.assertEqual(tag1_stats["total_report_count"], 4)
        self.assertEqual(tag1_stats["closed_report_count"], 2)  # fixed + rejected

        tag2_stats = tag_stats[1]
        self.assertEqual(tag2_stats["tag_name"], "Tag2")
        self.assertEqual(tag2_stats["total_report_count"], 3)
        self.assertEqual(tag2_stats["closed_report_count"], 2)  # fixed + rejected
