FROM python:3.12.4 as base

WORKDIR /app

RUN apt-get update && \
    apt-get install --yes libgdal-dev && \
    apt-get install --no-install-suggests --no-install-recommends --yes pipx && \
    apt-get install --yes --fix-missing graphviz

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.3.1 \
    # by default venv path would be set in /root folder and that would creates permission issues
    POETRY_VIRTUALENVS_PATH="/python_venv" \
    PATH="/root/.local/bin:${PATH}"



RUN pipx install poetry==${POETRY_VERSION}

COPY pyproject.toml poetry.lock ./
RUN poetry env use $(which python3)
# only install dev dependencies for testing and local development
ARG WITH_DEV_DEPENDENCIES=false
RUN poetry install $(test "$WITH_DEV_DEPENDENCIES" != true && echo "--only=main")

# create a symlink to the virtualenv and use it to set env variables
RUN ln -s $(poetry env info --path) /venv
# nice way to "activate" the virtual env https://pythonspeed.com/articles/activate-virtualenv-dockerfile/
ENV VIRTUAL_ENV=/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN useradd --no-create-home --system --uid 1000 --user-group worker

FROM base as app_web



COPY entrypoint.sh ./
ENTRYPOINT ["./entrypoint.sh"]

FROM base as app_worker
