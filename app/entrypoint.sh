#!/bin/sh

: "${POSTGRES_HOST:?is not set}"
: "${POSTGRES_PORT:?is not set}"

# depends_on conditions are only honoured by the compose CLI, not by the Docker
# daemon when it restarts containers (Docker Desktop startup), so wait here too.
attempts=0
until python -c "import os, socket; socket.create_connection((os.environ['POSTGRES_HOST'], int(os.environ['POSTGRES_PORT'])), 3).close()" 2>/dev/null; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 30 ]; then
        echo "Database still unreachable after 60s, giving up." >&2
        exit 1
    fi
    echo "Waiting for the database..."
    sleep 2
done

python manage.py migrate
python manage.py collectstatic --no-input
exec "$@"
