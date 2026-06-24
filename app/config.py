from dotenv import load_dotenv
import os

load_dotenv()


DB_DRIVER = os.getenv(
    "DB_DRIVER",
    "ODBC Driver 17 for SQL Server"
)

DB_SERVER = os.getenv("DB_SERVER")
DB_DATABASE = os.getenv("DB_DATABASE")
DB_UID = os.getenv("DB_UID")
DB_PWD = os.getenv("DB_PWD")

DB_TRUST_CERT = os.getenv(
    "DB_TRUST_SERVER_CERT",
    "yes"
)

DB_TIMEOUT_SECONDS = os.getenv(
    "DB_TIMEOUT_SECONDS",
    "5"
)

TABLE_NAME = os.getenv("TABLE_NAME")