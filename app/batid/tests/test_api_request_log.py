from datetime import timedelta
from unittest import mock

from batid.services.api_request_log import (
    TIME_BUDGET_SECONDS,
    delete_expired_api_request_logs,
)
from batid.tests.test_kpi import make_api_log
from django.test import TestCase
from django.utils import timezone
from rest_framework_tracking.models import APIRequestLog


def days_ago(days: int):
    return timezone.now() - timedelta(days=days)


class DeleteExpiredApiRequestLogs(TestCase):
    def test_deletes_only_rows_older_than_one_year(self):
        """
        Rows requested 400, 366, 364 and 1 days ago.
        Expected: returns 2, only the rows of 364 and 1 days ago remain.
        """
        make_api_log(days_ago(400))
        make_api_log(days_ago(366))
        recent = [make_api_log(days_ago(364)), make_api_log(days_ago(1))]

        self.assertEqual(delete_expired_api_request_logs(), 2)
        self.assertCountEqual(
            APIRequestLog.objects.values_list("id", flat=True),
            [log.id for log in recent],
        )

    def test_nothing_to_delete(self):
        """
        Only rows requested 364 and 1 days ago.
        Expected: returns 0, both rows remain.
        """
        make_api_log(days_ago(364))
        make_api_log(days_ago(1))

        self.assertEqual(delete_expired_api_request_logs(), 0)
        self.assertEqual(APIRequestLog.objects.count(), 2)

    @mock.patch("batid.services.api_request_log.BATCH_SIZE", 1)
    def test_stops_when_time_budget_is_spent(self):
        """
        Batches of 1 row, 3 old rows in chronological order, the clock is past the
        budget at the second batch check.
        Expected: returns 1, only the oldest row is deleted, 2 old rows remain.
        """
        oldest = make_api_log(days_ago(402))
        make_api_log(days_ago(401))
        make_api_log(days_ago(400))

        with mock.patch("batid.services.api_request_log.time") as fake_time:
            fake_time.monotonic.side_effect = [0, 0, TIME_BUDGET_SECONDS + 1]
            self.assertEqual(delete_expired_api_request_logs(), 1)

        self.assertFalse(APIRequestLog.objects.filter(id=oldest.id).exists())
        self.assertEqual(APIRequestLog.objects.count(), 2)

    @mock.patch("batid.services.api_request_log.BATCH_SIZE", 1)
    def test_batches_stop_at_the_newest_expired_row(self):
        """
        Batches of 1 row, 3 old rows then 2 recent rows.
        Expected: returns 3, the 3 old rows are deleted, the 2 recent rows remain.
        """
        for days in (402, 401, 400):
            make_api_log(days_ago(days))
        recent = [make_api_log(days_ago(2)), make_api_log(days_ago(1))]

        self.assertEqual(delete_expired_api_request_logs(), 3)
        self.assertCountEqual(
            APIRequestLog.objects.values_list("id", flat=True),
            [log.id for log in recent],
        )
