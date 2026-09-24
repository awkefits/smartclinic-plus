import os

import pymysql
from dotenv import load_dotenv

load_dotenv()

db_name = os.environ.get("DB_NAME", "smartclinic_plus")

connection = pymysql.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    user=os.environ.get("DB_USER", "root"),
    password=os.environ.get("DB_PASSWORD", ""),
)
with connection.cursor() as cursor:
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
    cursor.execute(f"USE `{db_name}`")

    with open("schema.sql") as schema_file:
        for command in schema_file.read().split(";"):
            if command.strip():
                cursor.execute(command)
connection.commit()
connection.close()
print(f"Database '{db_name}' and its tables are ready.")

from app import create_user, email_taken  

if email_taken("admin@smartclinic.test"):
    print("Admin account already exists.")
else:
    create_user("Admin", "admin@smartclinic.test", "admin123", "admin")
    print("Created admin account: admin@smartclinic.test / admin123")
