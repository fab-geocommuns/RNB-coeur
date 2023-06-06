#!/bin/sh

python manage.py migrate
python manage.py createsuperuser --noinput --username=paul --email=p.etienney@gmail.com

exec "$@"
