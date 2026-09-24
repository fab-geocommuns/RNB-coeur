import logging
from datetime import datetime, timedelta, timezone
from unittest import mock

from batid.services.candidate import (
    _maintenance_timestamps_are_stale,
    vacuum_analyze_candidates_if_needed,
)
from django.test import SimpleTestCase, TransactionTestCase

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)
FRESH = NOW - timedelta(days=1)
OLD = NOW - timedelta(days=60)


class MaintenanceTimestampsAreStaleTestCase(SimpleTestCase):
    def test_never_maintained_is_stale(self):
        """Input: all four pg_stat timestamps are None (table never vacuumed nor analyzed). Expected: stale."""
        self.assertTrue(
            _maintenance_timestamps_are_stale(None, None, None, None, now=NOW)
        )

    def test_fresh_manual_vacuum_and_analyze_is_not_stale(self):
        """Input: manual vacuum and analyze 1 day ago, no auto maintenance. Expected: not stale."""
        self.assertFalse(
            _maintenance_timestamps_are_stale(FRESH, None, FRESH, None, now=NOW)
        )

    def test_fresh_autovacuum_and_autoanalyze_is_not_stale(self):
        """Input: autovacuum and autoanalyze 1 day ago, no manual maintenance. Expected: not stale."""
        self.assertFalse(
            _maintenance_timestamps_are_stale(None, FRESH, None, FRESH, now=NOW)
        )

    def test_old_vacuum_with_fresh_analyze_is_stale(self):
        """Input: last vacuum 60 days ago but analyze 1 day ago. Expected: stale (vacuum overdue)."""
        self.assertTrue(
            _maintenance_timestamps_are_stale(OLD, None, FRESH, None, now=NOW)
        )

    def test_fresh_vacuum_with_old_analyze_is_stale(self):
        """Input: last vacuum 1 day ago but analyze 60 days ago. Expected: stale (analyze overdue)."""
        self.assertTrue(
            _maintenance_timestamps_are_stale(FRESH, None, OLD, None, now=NOW)
        )


class VacuumAnalyzeCandidatesIfNeededTestCase(TransactionTestCase):
    def test_vacuum_analyze_runs_when_stale(self):
        """Input: staleness check reports stale. Expected: VACUUM ANALYZE runs against the real database without logging any error."""
        with mock.patch(
            "batid.services.candidate._candidate_maintenance_is_stale",
            return_value=True,
        ):
            with self.assertNoLogs(level=logging.ERROR):
                vacuum_analyze_candidates_if_needed()


class VacuumAnalyzeCandidatesMockedTestCase(SimpleTestCase):
    def test_nothing_runs_when_fresh(self):
        """Input: staleness check reports fresh. Expected: no SQL is executed at all."""
        with mock.patch(
            "batid.services.candidate._candidate_maintenance_is_stale",
            return_value=False,
        ):
            with mock.patch("batid.services.candidate.connection") as connection:
                vacuum_analyze_candidates_if_needed()
                connection.cursor.assert_not_called()

    def test_fails_open_on_error(self):
        """Input: staleness check raises an exception. Expected: no exception propagates, the error is logged."""
        with mock.patch(
            "batid.services.candidate._candidate_maintenance_is_stale",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertLogs(level=logging.ERROR):
                vacuum_analyze_candidates_if_needed()


class InspectCandidatesTaskTestCase(SimpleTestCase):
    def test_maintenance_runs_before_inspection(self):
        """Input: the inspect_candidates task body. Expected: the vacuum/analyze step is called before Inspector.inspect."""
        manager = mock.Mock()
        with mock.patch(
            "batid.tasks.vacuum_analyze_candidates_if_needed", manager.vacuum
        ):
            with mock.patch("batid.tasks.Inspector", manager.Inspector):
                from batid.tasks import inspect_candidates

                inspect_candidates()

        self.assertEqual(manager.mock_calls[0], mock.call.vacuum())
        self.assertIn(mock.call.Inspector().inspect(), manager.mock_calls)
