from celery import Celery, signals
from jobs.dl_source import Downloader
from jobs.import_bdnb7 import import_bdnb7 as import_bdnb7_job
from jobs.import_bdtopo import import_bdtopo as import_bdtopo_job
from jobs.import_cities import import_etalab_cities
from jobs.inspect_candidates import Inspector
from jobs.remove_light_bdgs import remove_light_bdgs as remove_light_bdgs_job
from jobs.export import export_city as export_city_job
from jobs.remove_dpt import remove_dpt as remove_dpt_job

from tmp_jobs.id_format import change_id_format

import os
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration

broker_url = os.environ.get("CELERY_BROKER_URL")
backend_url = os.environ.get("CELERY_RESULT_BACKEND")
app = Celery("tasks", broker=broker_url, backend_url=backend_url)





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
def remove_dpt(dpt):
    remove_dpt_job(dpt)
    return "done"


@app.task
def remove_inspected_candidates():
    i = Inspector()
    i.remove_inspected()
    return "done"


@app.task
def import_cities(dpt):
    import_etalab_cities(dpt)
    # import_commune_insee_job(state_date)
    return "done"


@app.task
def remove_light_bdgs(dpt):
    remove_light_bdgs_job(dpt)
    return "done"


@app.task
def export_city(insee_code):
    export_city_job(insee_code)
    return "done"


@app.task
def tmp_change_id_format():
    change_len = change_id_format()
    if change_len > 0:
        app.send_task("tasks.tmp_change_id_format")
    return "done"
