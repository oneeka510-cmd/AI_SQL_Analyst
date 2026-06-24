from dotenv import load_dotenv
import pyodbc
import pandas as pd
load_dotenv()
import os
import warnings

warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy"
)
# Pyodbc connection with database 
# Read SQL connection values from .env
# load_dotenv() loads values from .env.
# os.getenv() reads those values.

DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
DB_SERVER = os.getenv("DB_SERVER")
DB_DATABASE = os.getenv("DB_DATABASE")
DB_UID = os.getenv("DB_UID")
DB_PWD = os.getenv("DB_PWD")
DB_TRUST_CERT = os.getenv("DB_TRUST_SERVER_CERT", "yes")
DB_TIMEOUT_SECONDS = os.getenv("DB_TIMEOUT_SECONDS", "5")

CONNECTION_STRING = (
    f"DRIVER={{{DB_DRIVER}}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_DATABASE};"
    f"UID={DB_UID};"
    f"PWD={DB_PWD};"
    f"TrustServerCertificate={DB_TRUST_CERT};"
    f"Connection Timeout={DB_TIMEOUT_SECONDS};"
)

# Connect once.
conn = pyodbc.connect(CONNECTION_STRING)



#Cursor = used to run SQL queries
#SELECT 1 is commonly used to:Check if DB is alive Doesn’t depend on any table Very fast
#cursor.fetchone() Actually fetch result

table_name=  "[dbo].[temp_tbl_Event_Data]"
master_df = pd.read_sql(
    "SELECT TOP 1 * FROM [dbo].[temp_tbl_Event_Data] ",
    conn
)

# print(master_df)
# column_list=master_df.columns.tolist()


sample_df = pd.read_sql(
    "SELECT TOP 5 * FROM [dbo].[temp_tbl_Event_Data]",
    conn
)

sample_rows = sample_df.to_string(index=False)

# Column names + dtypes
dtype_info = "\n".join(
    [f"{col}: {dtype}" for col, dtype in sample_df.dtypes.items()]
)


query=input("Enter you query?")
#Gernerate sql query from gpt by passing it column_list and user question

from langchain_openai import ChatOpenAI

model= ChatOpenAI()

prompt= f"""You are a maritime expret, I am providing you a list containig the column names and a user query,
 based on the user query write a sql server query by refering the column names provided to you

 #table name
 {table_name}

# Columns and Data Types
{dtype_info}

# Sample Rows
{sample_rows}

#User question:
 {query}

When the user asks for total, use SUM().
When filtering by vessel name, use LIKE and % sign before first word, in middle of two words and at the end of name. 
Return only SQL Server Query do not use keywords like LIMIT which are not for sql server.
Use exact column names provided.
Do not invent column names.
"""

result=model.invoke(prompt)
sql_query = result.content

sql_query = sql_query.replace("```sql", "")
sql_query = sql_query.replace("```", "")
sql_query = sql_query.strip()



#Add Vlidation before executing in sql directly 
# if not sql_query.upper().startswith("SELECT"):
#     raise Exception("Only SELECT queries allowed")
#result_df = pd.read_sql(sql_query, conn) # right now not executing this directly because gpt is making mistakes



print(sql_query)



#Adding all the leftover tables here:
# temp_tbl_CII_Leg_Wise
# [dbo].[temp_tbl_CII_Month_Wise]
# [dbo].[temp_tbl_CII_Voyage_Wise]
# [dbo].[temp_tbl_CII_Year_Wise]




