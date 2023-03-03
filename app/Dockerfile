FROM python:3.10

ENV HOME=/app

RUN mkdir -p $HOME
RUN mkdir -p /tmp/buffers


WORKDIR $HOME

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update
RUN apt-get install --yes libgdal-dev


RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

COPY . .