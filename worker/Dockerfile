FROM python:3.10

WORKDIR /worker

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH "${PYTHONPATH}:/worker"

RUN apt-get update
RUN apt-get install --yes libgdal-dev

RUN pip install --upgrade pip
COPY ./worker/requirements.txt .
RUN pip install -r requirements.txt

COPY ./shared_libs /shared_libs
ENV PYTHONPATH "${PYTHONPATH}:/shared_libs"

# COPY . .