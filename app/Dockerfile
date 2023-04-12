FROM python:3.10

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update
RUN apt-get install --yes libgdal-dev

RUN pip install --upgrade pip
COPY ./app/requirements.txt .
RUN pip install -r requirements.txt

#COPY ./app
COPY ./shared_libs /shared_libs
ENV PYTHONPATH "${PYTHONPATH}:/shared_libs"

COPY ./app/entrypoint.sh .
RUN chmod +x  ./entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
