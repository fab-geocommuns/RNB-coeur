import psycopg2
import os

db_name = os.environ.get("SQL_NAME")
db_user = os.environ.get("SQL_USER")
db_password = os.environ.get("SQL_PASSWORD")

conn = psycopg2.connect(f"dbname='{db_name}' user='{db_user}' host='db' password='{db_password}'")