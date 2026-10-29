import os

from celery import Celery
from celery.signals import task_failure

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

app = Celery("app")


# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@task_failure.connect
def notify_task_failure(*, sender, task_id, exception, **_kwargs) -> None:
    """
    Notify the tech team when any task fails for good.

    task_failure is sent once per final failure: not on autoretry_for attempts (they
    send task_retry), and also when the worker process dies (e.g. OOM kill). Celery
    logs an exception raised here without changing the task state.
    """
    # Imported here: this module is loaded with the settings, before Django apps are ready.
    from batid.services.tchap import notify_tech

    notify_tech(f"Error while executing {sender.name} ({task_id}): {exception}")
