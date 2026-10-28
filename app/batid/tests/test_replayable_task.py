from unittest import mock

from batid.services.replayable_task import (
    ReplayableTask,
    release_replayable_task_lock,
)
from celery import states
from celery.exceptions import Ignore
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
