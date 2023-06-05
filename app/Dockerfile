FROM python:3.10 as app

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update
RUN apt-get install --yes libgdal-dev

RUN pip install --upgrade pip
COPY ./app/requirements.txt .
RUN pip install -r requirements.txt

# COPY ./shared_libs /shared_libs
# ENV PYTHONPATH "${PYTHONPATH}:/shared_libs"

FROM app as app_web

COPY ./app/entrypoint.sh .
RUN chmod +x  ./entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

FROM app as app_worker
