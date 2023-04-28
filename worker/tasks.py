from celery import Celery, signals
from jobs.dl_source import Downloader
from jobs.import_bdnb7 import import_bdnb7 as import_bdnb7_job
from jobs.import_bdtopo import import_bdtopo as import_bdtopo_job
from jobs.import_commune_insee import import_commune_insee as import_commune_insee_job
from jobs.inspect_candidates import Inspector
from jobs.remove_light_bdgs import remove_light_bdgs as remove_light_bdgs_job
from jobs.export import export_city as export_city_job
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


@app.task
def import_commune_insee(state_date):
    import_commune_insee_job(state_date)
    return "done"


@app.task
def remove_light_bdgs(dpt):
    remove_light_bdgs_job(dpt)
    return "done"


@app.task
def export_city(insee_code):
    export_city_job(insee_code)
    return "done"
