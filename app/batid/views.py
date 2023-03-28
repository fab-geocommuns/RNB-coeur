from django.shortcuts import render
from app.celery import app as celery_app

def worker(request):

    i = celery_app.control.inspect()
    active_tasks = i.active()

    return render(request, 'admin/tasks.html', {
        'active_tasks': active_tasks,
    })