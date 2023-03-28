#!/bin/sh

# python manage.py flush --no-input
python manage.py migrate
python manage.py createsuperuser --noinput --username=paul --email=p.etienney@gmail.com
python manage.py collectstatic --noinput

exec "$@"
