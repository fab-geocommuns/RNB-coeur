from celery import Task, states
from celery.exceptions import Ignore
from django.db import connections


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
        db = connections["default"]
        lock_connection = db.get_new_connection(db.get_connection_params())
        lock_connection.autocommit = True
        setattr(self.request, "replayable_task_lock", lock_connection)
        lock_connection.execute(
            "SELECT pg_advisory_lock(hashtext(%s))", [f"celery_task:{task_id}"]
        )

        if self.AsyncResult(task_id).state == states.SUCCESS:
            raise Ignore()


def release_replayable_task_lock(request) -> None:
    """To call once the task state is stored (task_postrun)."""
    lock_connection = getattr(request, "replayable_task_lock", None)
    if lock_connection is not None:
        lock_connection.close()
