from celery import Celery
import os

broker_url = os.environ.get("CELERY_BROKER_URL")
backend_url = os.environ.get("CELERY_RESULT_BACKEND")
app = Celery('tasks', broker=broker_url, backend_url=backend_url)

@app.task
def add(x, y):
    return x + y