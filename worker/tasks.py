from celery import Celery
from jobs.import_bdnb7 import import_bdnb7 as import_bdnb7_job
from jobs.import_bdtopo import import_bdtopo as import_bdtopo_job
from jobs.import_cities import import_etalab_cities
from jobs.inspect_candidates import Inspector
from jobs.remove_light_bdgs import remove_light_bdgs as remove_light_bdgs_job
from jobs.export import export_city as export_city_job
from jobs.remove_dpt import remove_dpt as remove_dpt_job
from jobs.status import add_default_status as add_default_status_job
from tmp_jobs.id_format import change_id_format
import os

broker_url = os.environ.get("CELERY_BROKER_URL")
backend_url = os.environ.get("CELERY_RESULT_BACKEND")
app = Celery("tasks", broker=broker_url, backend_url=backend_url)








@app.task(queue="bdg_signals")
def handle_signal(signal_id):
    return f"handled signal : {signal_id}"


@app.task
def tmp_change_id_format():
    change_len = change_id_format()
    if change_len > 0:
        app.send_task("tasks.tmp_change_id_format")
    return "done"
