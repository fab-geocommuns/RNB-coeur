FROM python:3.10.14 as base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=1.3.1

RUN apt-get update
RUN apt-get install --yes libgdal-dev
RUN apt-get install --no-install-suggests --no-install-recommends --yes pipx
ENV PATH="/root/.local/bin:${PATH}"
RUN pipx install poetry==${POETRY_VERSION}

# check python version is 3.10.14
# RUN if [ "$(python3 --version)" != "Python 3.10.14" ]; then echo "Python version is not 3.10.14"; exit 1; fi
COPY . .
RUN poetry env use $(which python3)
RUN poetry install

RUN ln -s $(poetry env info --path) /venv
# https://pythonspeed.com/articles/activate-virtualenv-dockerfile/
ENV VIRTUAL_ENV=/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# deactivate the creation of a specific user for the moment
# is it usefull in docker anyway?
# RUN useradd --no-create-home --system --uid 1000 --user-group worker

FROM base as app_web
ENTRYPOINT ["./entrypoint.sh"]

FROM base as app_worker
