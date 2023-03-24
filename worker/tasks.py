from celery import Celery
from jobs.dl_source import Downloader
import os

broker_url = os.environ.get("CELERY_BROKER_URL")
backend_url = os.environ.get("CELERY_RESULT_BACKEND")
app = Celery('tasks', broker=broker_url, backend_url=backend_url)

@app.task
def dl_source(src, dpt):
    dl = Downloader(src, dpt)
    dl.download()
    dl.uncompress()
    return 'done'

@app.task
def add(x, y):
    return x + y