FROM python:3.10

ENV HOME=/home/app

RUN mkdir -p $HOME
RUN mkdir -p $HOME/buffers
# RUN mkdir -p $HOME/import_data
RUN adduser --system --group app

WORKDIR $HOME

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update
RUN apt-get install --yes libgdal-dev


RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

COPY . $HOME

RUN chown -R app:app $HOME

# change to the app user
USER app
