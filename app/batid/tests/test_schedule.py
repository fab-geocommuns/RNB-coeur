from datetime import datetime, timezone

from django.test import SimpleTestCase

from app.schedule import production_schedule

# Not in January, April, July or October: Celery never reads the clock from this date
AFTER = datetime(2026, 11, 16, tzinfo=timezone.utc)


def next_run(entry_name: str) -> datetime:
    """Next run of a production beat entry after AFTER, computed by Celery."""
    schedule = production_schedule[entry_name]["schedule"]
    last_run_at, delta, _now = schedule.remaining_delta(AFTER)
    return last_run_at + delta


class QuarterlyImportsScheduleTest(SimpleTestCase):
    def test_bdtopo_import_runs_on_the_third_monday(self):
        """
        Input: production schedule, last run on Monday 16/11/2026 00:00 UTC.
        Expected: the next BD Topo import is on Monday 18/01/2027 00:00 UTC.
        """
        self.assertEqual(
            next_run("import_bdtopo"),
            datetime(2027, 1, 18, tzinfo=timezone.utc),
        )

    def test_plots_import_runs_on_the_fourth_monday(self):
        """
        Input: production schedule, last run on Monday 16/11/2026 00:00 UTC.
        Expected: the next cadastre import is on Monday 25/01/2027 00:00 UTC.
        """
        self.assertEqual(
            next_run("import_plots"),
            datetime(2027, 1, 25, tzinfo=timezone.utc),
        )
