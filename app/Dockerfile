FROM python:3.10 as app

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update
RUN apt-get install --yes libgdal-dev

RUN pip install --upgrade pip
COPY ./app/requirements.txt .
RUN pip install -r requirements.txt

FROM app as app_web

## Add the wait script to the image
COPY --from=ghcr.io/ufoscout/docker-compose-wait:latest /wait /wait

COPY ./app/entrypoint.sh .
RUN chmod +x  ./entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

FROM app as app_worker
