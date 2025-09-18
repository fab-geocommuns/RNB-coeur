#!/bin/sh

python manage.py migrate
python manage.py collectstatic --no-input

pygeoapi openapi generate --config ${PYGEOAPI_CONFIG} --output ${PYGEOAPI_OPENAPI} --force

exec "$@"
