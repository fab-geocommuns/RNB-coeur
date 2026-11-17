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

# Tasks whose arguments hold personal data (name, e-mail, username): never sent to Tchap
TASKS_WITH_SENSITIVE_ARGS = frozenset(
    {"batid.tasks.create_sandbox_user", "batid.tasks.remove_light_buildings"}
)
ARGS_MAX_LENGTH = 500


@task_failure.connect
def notify_task_failure(*, sender, task_id, exception, args, kwargs, **_kwargs) -> None:
    """
    Notify the tech team when any task fails for good.

    task_failure is sent once per final failure: not on autoretry_for attempts (they
    send task_retry), and also when the worker process dies (e.g. OOM kill). Celery
    logs an exception raised here without changing the task state.
    """
    # Imported here: this module is loaded with the settings, before Django apps are ready.
    from batid.services.tchap import Code, TchapLevel, notify_tech

    notify_tech(
        level=TchapLevel.FAILURE,
        title="Échec de la tâche",
        details=[
            ("Tâche", Code(sender.name)),
            ("Identifiant", Code(str(task_id))),
            (
                "Arguments",
                Code(_task_arguments(sender=sender, args=args, kwargs=kwargs)),
            ),
        ],
        # Some exceptions carry no message, e.g. BANAPIDown()
        error=str(exception) or type(exception).__name__,
    )


def _task_arguments(*, sender, args, kwargs) -> str:
    if sender.name in TASKS_WITH_SENSITIVE_ARGS:
        return "masqués"
    if not args and not kwargs:
        return "aucun"
    text = ", ".join(
        [repr(a) for a in args or ()]
        + [f"{k}={v!r}" for k, v in (kwargs or {}).items()]
    )
    if len(text) > ARGS_MAX_LENGTH:
        text = text[: ARGS_MAX_LENGTH - 1] + "…"
    return text
