import pyodbc
import pandas as pd

from app.config import (
    DB_DRIVER,
    DB_SERVER,
    DB_DATABASE,
    DB_UID,
    DB_PWD,
    DB_TRUST_CERT,
    DB_TIMEOUT_SECONDS
)


def get_connection_string():

    return (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_DATABASE};"
        f"UID={DB_UID};"
        f"PWD={DB_PWD};"
        f"TrustServerCertificate={DB_TRUST_CERT};"
        f"Connection Timeout={DB_TIMEOUT_SECONDS};"
    )


def get_connection():
    return pyodbc.connect(get_connection_string())


def get_table_context(conn, table_name):

    sample_df = pd.read_sql(
        f"SELECT TOP 5 * FROM {table_name}",
        conn
    )

    sample_rows = sample_df.to_string(index=False)

    dtype_info = "\n".join(
        f"{column}: {dtype}"
        for column, dtype
        in sample_df.dtypes.items()
    )

    return dtype_info, sample_rows


def execute_query(sql_query):

    conn = get_connection()

    try:
        result_df = pd.read_sql(
            sql_query,
            conn
        )

        return result_df

    finally:
        conn.close()