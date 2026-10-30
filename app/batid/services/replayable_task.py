import logging

from celery import Task, states
from celery.exceptions import Ignore
from django.db import connections

logger = logging.getLogger(__name__)


class ReplayableTask(Task):
    """Base of the tasks that a deploy may interrupt and that are safe to run again.

    acks_late: the message is acked when the task ends, not when it starts. If a
    deploy kills the worker mid-task, RabbitMQ redelivers it to the new worker. Never
    use it for sending tasks: an email would be sent twice.

    A task id succeeds at most once, even when its message is delivered twice: a
    redelivery after its success was stored, or the next step of a chain sent again by
    a replayed task (chain ids are fixed when the chain is created). The runs of an id
    are serialized by a Postgres session lock, held on a dedicated connection until
    the task state is stored (see release_replayable_task_lock): a killed worker
    closes that connection, which releases the lock.
    """

    acks_late = True

    def before_start(self, task_id, args, kwargs):
        try:
            db = connections["default"]
            lock_connection = db.get_new_connection(db.get_connection_params())
            setattr(self.request, "replayable_task_lock", lock_connection)
            lock_connection.autocommit = True
            # The worker statement_timeout would cancel the wait for a run that
            # lasts hours
            lock_connection.execute("SET statement_timeout = 0")
            lock_connection.execute(
                "SELECT pg_advisory_lock(hashtext(%s))", [f"celery_task:{task_id}"]
            )
        except Exception as exc:
            # autoretry_for only covers the task body: a database outage must not
            # ack and lose the message. Same retry limit as the body.
            raise self.retry(exc=exc, **getattr(self, "retry_kwargs", {}))

        try:
            already_successful = self.AsyncResult(task_id).state == states.SUCCESS
        except Exception:
            # Redis down: run anyway, as before this base. The task is safe to run
            # again and the lock still serializes its runs.
            logger.warning(
                "Task %s state unreadable, run without the success check",
                task_id,
                exc_info=True,
            )
            already_successful = False

        if already_successful:
            raise Ignore()


def release_replayable_task_lock(request) -> None:
    """To call once the task state is stored (task_postrun)."""
    lock_connection = getattr(request, "replayable_task_lock", None)
    if lock_connection is not None:
        lock_connection.close()
