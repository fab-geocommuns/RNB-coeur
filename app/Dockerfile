FROM python:3.14.5 as base

WORKDIR /app

RUN apt-get update && \
    apt-get install --yes libgdal-dev && \
    apt-get install --no-install-suggests --no-install-recommends --yes pipx ca-certificates

# pip < 26.2.2 trusts the compromised eMudhra/emSign CA through its vendored certifi.
# Install the fixed wheel pinned by hash, so a MITM cannot tamper with it.
RUN python3 -m pip install --no-cache-dir \
    "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # make pip (including the one used by pipx) verify TLS against the up-to-date system CA store
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    POETRY_VERSION=2.2.1 \
    # by default venv path would be set in /root folder and that would creates permission issues
    POETRY_VIRTUALENVS_PATH="/python_venv" \
    PATH="/root/.local/bin:${PATH}"

RUN pipx install --python=python3 poetry==${POETRY_VERSION}

COPY pyproject.toml poetry.lock ./
RUN poetry env use $(which python3)

# Only needed to regenerate the poetry.lock file in case of conflicts.
# RUN poetry lock

# only install dev dependencies for testing and local development
ARG WITH_DEV_DEPENDENCIES=false
RUN poetry install $(test "$WITH_DEV_DEPENDENCIES" != true && echo "--only=main")

# create a symlink to the virtualenv and use it to set env variables
RUN ln -s $(poetry env info --path) /venv
# nice way to "activate" the virtual env https://pythonspeed.com/articles/activate-virtualenv-dockerfile/
ENV VIRTUAL_ENV=/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# From Redis Dockerfile: https://github.com/redis/docker-library-redis/blob/master/Dockerfile.template#L12
# -r creates a system user and group. 999 as uid/gid seems to be the default for system users.
# From man:
#   System users will be created with no aging information in /etc/shadow, and their numeric identifiers are choosen
#   in the SYS_UID_MIN-SYS_UID_MAX range, defined in /etc/login.defs, instead of UID_MIN-UID_MAX (and their GID counterparts
#   for the creation of groups).
#   Note that useradd will not create a home directory for such an user, regardless of the default setting in /etc/login.defs
#   (CREATE_HOME). You have to specify the -m options if you want a home directory for a system account to be created.
RUN groupadd -r -g 999 app && \
    useradd -r -g app -u 999 app

COPY --chown=999:999 . /app
RUN mkdir /app/data
RUN chown 999:999 /app/data

USER app

FROM base as app_web
ENTRYPOINT ["./entrypoint.sh"]

FROM base as app_worker
