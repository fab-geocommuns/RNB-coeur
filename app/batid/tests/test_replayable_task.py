from unittest import mock

from batid.services.replayable_task import (
    ReplayableTask,
    release_replayable_task_lock,
)
from batid.tasks import end_replayable_task
from celery import states
from celery.exceptions import Ignore, Retry
from django.db import connections
from django.test import TestCase

from app.celery import app as celery_app


@celery_app.task(base=ReplayableTask, name="batid.tests.test_replayable_task.noop")
def noop() -> None:
    pass


class TestReplayableTask(TestCase):
    TASK_ID = "replayable-task-test-id"

    def setUp(self):
        noop.push_request(id=self.TASK_ID)
        self.addCleanup(noop.pop_request)
        self.addCleanup(release_replayable_task_lock, noop.request)

    def _lock_is_free(self) -> bool:
        db = connections["default"]
        other = db.get_new_connection(db.get_connection_params())
        try:
            row = other.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s))",
                [f"celery_task:{self.TASK_ID}"],
            ).fetchone()
            return row[0]
        finally:
            other.close()

    def _start_with_state(self, state: str) -> None:
        with mock.patch.object(noop, "AsyncResult") as async_result:
            async_result.return_value.state = state
            noop.before_start(self.TASK_ID, (), {})

    def test_id_already_successful_is_ignored(self):
        """
        Input: a task id whose success is already stored (redelivery after success,
        or a chain step sent twice).
        Expected: Ignore is raised, so the task body does not run again.
        """
        with self.assertRaises(Ignore):
            self._start_with_state(states.SUCCESS)

    def test_id_not_successful_runs_and_holds_the_lock_until_released(self):
        """
        Input: a task id killed or retried before its success (state STARTED, RETRY).
        Expected: the task runs; another run of the id waits on the lock until the
        task state is stored and the lock released.
        """
        for state in [states.STARTED, states.RETRY]:
            self._start_with_state(state)

            self.assertFalse(self._lock_is_free())
            release_replayable_task_lock(noop.request)
            self.assertTrue(self._lock_is_free())

    def test_acks_late(self):
        """
        Input: a task based on ReplayableTask.
        Expected: its message is acked when it ends, not when it starts.
        """
        self.assertTrue(noop.acks_late)

    def test_lock_wait_is_not_cut_by_the_statement_timeout(self):
        """
        Input: a worker whose connections have a statement_timeout (15 s in prod).
        Expected: the lock connection waits without limit (statement_timeout 0).
        """
        self._start_with_state(states.STARTED)

        lock_connection = noop.request.replayable_task_lock
        row = lock_connection.execute("SHOW statement_timeout").fetchone()
        self.assertEqual(row[0], "0")

    def test_redis_outage_retries_instead_of_failing(self):
        """
        Input: the task state cannot be read (Redis down) when the task starts.
        Expected: the task is retried (Retry raised), not failed and acked.
        """
        with mock.patch.object(noop, "AsyncResult") as async_result:
            type(async_result.return_value).state = mock.PropertyMock(
                side_effect=ConnectionError("redis down")
            )
            with mock.patch.object(noop, "retry", side_effect=Retry()) as retry:
                with self.assertRaises(Retry):
                    noop.before_start(self.TASK_ID, (), {})

        self.assertIsInstance(retry.call_args.kwargs["exc"], ConnectionError)

    def test_lock_released_even_if_file_removal_fails(self):
        """
        Input: the removal of the consumed files raises at the end of the task.
        Expected: the lock is released anyway.
        """
        self._start_with_state(states.STARTED)

        with mock.patch(
            "batid.tasks.remove_paths_of_successful_task",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaises(PermissionError):
                end_replayable_task(task=noop, state=states.SUCCESS)

        self.assertTrue(self._lock_is_free())
