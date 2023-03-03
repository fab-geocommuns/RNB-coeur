FROM python:3.10

ENV HOME=/app

RUN mkdir -p $HOME

WORKDIR $HOME

RUN adduser --system --group app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update
RUN apt-get install --yes libgdal-dev

RUN mkdir /app/data/buffers

RUN chown -R app:app $HOME

RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

USER app

COPY . .

