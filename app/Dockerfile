FROM python:3.10.14 as base

WORKDIR /app

RUN apt-get update && \
    apt-get install --yes libgdal-dev && \
    apt-get install --no-install-suggests --no-install-recommends --yes pipx

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.3.1 \
    PATH="/root/.local/bin:${PATH}"

RUN pipx install poetry==${POETRY_VERSION}

# we first copy pyproject.toml and poetry.lock to leverage docker cache
COPY pyproject.toml poetry.lock ./
RUN poetry env use $(which python3)
RUN poetry install

RUN ln -s $(poetry env info --path) /venv
# https://pythonspeed.com/articles/activate-virtualenv-dockerfile/
ENV VIRTUAL_ENV=/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
COPY . .

# deactivate the creation of a specific user for the moment
# is it usefull in docker anyway?
# RUN useradd --no-create-home --system --uid 1000 --user-group worker

FROM base as app_web
ENTRYPOINT ["./entrypoint.sh"]

FROM base as app_worker
