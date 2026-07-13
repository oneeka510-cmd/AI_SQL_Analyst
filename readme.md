# SQL AI Analyst

Ask questions in plain English and get safe, read-only answers from one SQL Server table.

This project is built for the common reporting setup where Power BI or an upstream process has already joined the business data into a single table. The assistant reads that table schema, asks an LLM to produce SQL Server syntax, validates the generated SQL, executes it, and explains the result in plain English.

## Current Scope

- Database: Microsoft SQL Server
- UI: Streamlit
- Data model: exactly one configured table
- SQL policy: read-only `SELECT` queries only
- Blocked by design: joins, writes, stored procedures, temp tables, unrelated tables, and multi-statement SQL

## Features

- Natural-language to SQL generation
- Rich schema-aware prompting from live SQL Server metadata
- Conservative SQL validation before execution
- One automatic query repair attempt if validation or execution fails
- Plain-English result explanation
- Sidebar schema browser and sample-row preview
- Query history for the current Streamlit session
- Result metrics, quick bar charts, and full data table view
- CSV and Excel downloads
- Configurable table, model, row cap, and schema sample size

## How It Works

```text
User question
      |
Read configured table schema
      |
Generate single-table SQL Server SELECT
      |
Validate read-only SQL guardrails
      |
Execute query
      |
Explain, chart, and export results
```

## Tech Stack

- Python
- SQL Server
- Streamlit
- LangChain OpenAI
- Pandas
- PyODBC
- OpenPyXL

## Installation

Create and activate a virtual environment:

```bash
python -m venv sqvenv
sqvenv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root.

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o

DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=localhost
DB_DATABASE=sample_database
DB_UID=username
DB_PWD=password
DB_TRUST_SERVER_CERT=yes
DB_TIMEOUT_SECONDS=5

DEFAULT_TABLE=[dbo].[sample_table]
DEFAULT_ROW_LIMIT=1000
SCHEMA_SAMPLE_ROWS=8
```

`DB_DATABASE` and `DEFAULT_TABLE` are used as the default selections in the Streamlit sidebar. Users can type a different database name and table name at runtime without editing `.env`, as long as the same SQL Server credentials can access them.

## Running

From the project root:

```bash
streamlit run app.py
```

## Example Questions

- How many records are in this table?
- Show the latest month of records for vessel X.
- What is the total fuel consumption by vessel for January 2025?
- Which records have the highest fuel consumption?
- Show the monthly record count for the latest year in the data.

## Notes

Generated SQL is validated before execution, but this is still an assistant-driven analytics tool. Keep database permissions read-only for the configured user in production.
