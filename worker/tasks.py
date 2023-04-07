from celery import Celery, signals
from jobs.dl_source import Downloader
from jobs.import_bdnb7 import import_bdnb7 as import_bdnb7_job
from jobs.import_bdtopo import import_bdtopo as import_bdtopo_job
from jobs.inspect_candidates import Inspector
import os
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration

broker_url = os.environ.get("CELERY_BROKER_URL")
backend_url = os.environ.get("CELERY_RESULT_BACKEND")
app = Celery("tasks", broker=broker_url, backend_url=backend_url)


@signals.celeryd_init.connect
def init_sentry(**_kwargs):
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_WORKER_DSN"),
        integrations=[
            CeleryIntegration(),
        ],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production,
        traces_sample_rate=1.0,
    )


@app.task
def dl_source(src, dpt):
    dl = Downloader(src, dpt)
    dl.download()
    dl.uncompress()
    return "done"


@app.task
def import_bdnb7(dpt):
    import_bdnb7_job(dpt)
    return "done"


@app.task
def import_bdtopo(dpt):
    import_bdtopo_job(dpt)
    return "done"


@app.task
def inspect_candidates():
    i = Inspector()
    inspections_len = i.inspect()
    if inspections_len > 0:
        app.send_task("tasks.inspect_candidates")
    return "done"
