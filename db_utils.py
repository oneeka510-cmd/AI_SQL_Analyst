"""
Backend utilities for the Streamlit SQL assistant.

The project is intentionally scoped to one SQL Server table. Keeping that
boundary explicit lets the app give the model rich schema context while still
blocking unsafe or unrelated SQL before anything reaches the database.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
import pyodbc
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


DEFAULT_TABLE = "[dbo].[temp_tbl_Event_Data]"
TABLE_NAME = os.getenv("DEFAULT_TABLE", DEFAULT_TABLE).strip() or DEFAULT_TABLE
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
DEFAULT_ROW_LIMIT = int(os.getenv("DEFAULT_ROW_LIMIT", "1000"))
SCHEMA_SAMPLE_ROWS = int(os.getenv("SCHEMA_SAMPLE_ROWS", "8"))

DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
DB_SERVER = os.getenv("DB_SERVER")
DB_DATABASE = os.getenv("DB_DATABASE")
DB_UID = os.getenv("DB_UID")
DB_PWD = os.getenv("DB_PWD")
DB_TRUST_CERT = os.getenv("DB_TRUST_SERVER_CERT", "yes")
DB_TIMEOUT_SECONDS = os.getenv("DB_TIMEOUT_SECONDS", "5")


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    max_length: int | None = None
    precision: int | None = None
    scale: int | None = None

    @property
    def sql_name(self) -> str:
        return quote_identifier(self.name)

    @property
    def type_label(self) -> str:
        lower_type = self.data_type.lower()
        if lower_type in {"varchar", "nvarchar", "char", "nchar"}:
            length = "max" if self.max_length == -1 else self.max_length
            return f"{self.data_type}({length})"
        if lower_type in {"decimal", "numeric"}:
            return f"{self.data_type}({self.precision},{self.scale})"
        return self.data_type


def validate_database_name(database_name: str | None) -> str:
    """Reject values that could break out of the ODBC connection-string field."""
    cleaned = (database_name or "").strip()
    if not cleaned:
        raise ValueError("Database name is required.")
    if any(char in cleaned for char in ";{}"):
        raise ValueError("Database name cannot contain semicolons or braces.")
    return cleaned


def build_connection_string(database_name: str | None = None) -> str:
    database = validate_database_name(database_name or DB_DATABASE)
    return (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={database};"
        f"UID={DB_UID};"
        f"PWD={DB_PWD};"
        f"TrustServerCertificate={DB_TRUST_CERT};"
        f"Connection Timeout={DB_TIMEOUT_SECONDS};"
    )


CONNECTION_STRING = build_connection_string(DB_DATABASE) if DB_DATABASE else ""


def get_connection(database_name: str | None = None) -> pyodbc.Connection:
    """Open one fresh pyodbc connection. Caller is responsible for closing it."""
    return pyodbc.connect(build_connection_string(database_name))


def _identifier_parts(raw_identifier: str) -> list[str]:
    token = r"(?:\[[^\]]+\]|[A-Za-z_][\w$#]*)"
    if not re.fullmatch(rf"\s*{token}(?:\s*\.\s*{token}){{0,2}}\s*", raw_identifier):
        raise ValueError(f"Invalid SQL Server table identifier: {raw_identifier!r}")
    parts = re.findall(r"\[([^\]]+)\]|([A-Za-z_][\w$#]*)", raw_identifier)
    cleaned = [bracketed or bare for bracketed, bare in parts]
    if not cleaned:
        raise ValueError(f"Invalid SQL Server table identifier: {raw_identifier!r}")
    return cleaned


def quote_identifier(identifier: str) -> str:
    return f"[{identifier.replace(']', ']]')}]"


def quote_table_name(raw_table_name: str = TABLE_NAME) -> str:
    return ".".join(quote_identifier(part) for part in _identifier_parts(raw_table_name))


def object_id_name(raw_table_name: str = TABLE_NAME) -> str:
    return ".".join(_identifier_parts(raw_table_name))


def _format_schema(columns: list[ColumnInfo]) -> str:
    lines = []
    for col in columns:
        nullable = "nullable" if col.nullable else "not null"
        lines.append(f"- {col.sql_name}: {col.type_label}, {nullable}")
    return "\n".join(lines)


def _format_sample_rows(sample_df: pd.DataFrame) -> str:
    if sample_df.empty:
        return "(table returned no sample rows)"
    return sample_df.to_string(index=False, max_cols=80, max_colwidth=80)


def get_schema_info(
    conn: pyodbc.Connection,
    table_name: str | None = None,
    sample_rows: int = SCHEMA_SAMPLE_ROWS,
) -> dict[str, Any]:
    """
    Return structured schema details and a small sample from the configured table.

    The returned dict is designed for both the prompt and the Streamlit sidebar.
    """
    raw_table_name = table_name or TABLE_NAME
    quoted_table = quote_table_name(raw_table_name)
    metadata_sql = """
        SELECT
            c.name AS column_name,
            t.name AS data_type,
            c.max_length,
            c.precision,
            c.scale,
            c.is_nullable
        FROM sys.columns AS c
        INNER JOIN sys.types AS t
            ON c.user_type_id = t.user_type_id
        WHERE c.object_id = OBJECT_ID(?)
        ORDER BY c.column_id;
    """
    metadata_df = pd.read_sql(metadata_sql, conn, params=[object_id_name(raw_table_name)])
    if metadata_df.empty:
        raise ValueError(
            f"Could not read columns for {raw_table_name}. Check the table name and database permissions."
        )

    columns = [
        ColumnInfo(
            name=str(row.column_name),
            data_type=str(row.data_type),
            nullable=bool(row.is_nullable),
            max_length=None if pd.isna(row.max_length) else int(row.max_length),
            precision=None if pd.isna(row.precision) else int(row.precision),
            scale=None if pd.isna(row.scale) else int(row.scale),
        )
        for row in metadata_df.itertuples(index=False)
    ]

    sample_df = pd.read_sql(f"SELECT TOP {int(sample_rows)} * FROM {quoted_table}", conn)
    return {
        "table_name": quoted_table,
        "raw_table_name": raw_table_name,
        "object_id_name": object_id_name(raw_table_name),
        "columns": columns,
        "column_names": [col.name for col in columns],
        "schema_text": _format_schema(columns),
        "sample_rows": _format_sample_rows(sample_df),
        "sample_df": sample_df,
    }


def _llm() -> ChatOpenAI:
    return ChatOpenAI(model=OPENAI_MODEL, temperature=0)


def _clean_llm_sql(content: str) -> str:
    cleaned = content.replace("```sql", "").replace("```", "").strip()
    return cleaned.rstrip(";").strip()


def _schema_text(schema_info_or_text: dict[str, Any] | str) -> str:
    if isinstance(schema_info_or_text, dict):
        return str(schema_info_or_text["schema_text"])
    return str(schema_info_or_text)


def _sample_text(schema_info_or_text: dict[str, Any] | str, fallback: str | None) -> str:
    if isinstance(schema_info_or_text, dict):
        return str(schema_info_or_text["sample_rows"])
    return fallback or ""


def generate_sql(
    question: str,
    schema_info_or_text: dict[str, Any] | str,
    sample_rows: str | None = None,
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> str:
    """
    Convert a natural-language question into a SQL Server SELECT statement.

    Returns the SQL string, or the literal text INSUFFICIENT_COLUMNS.
    """
    schema_text = _schema_text(schema_info_or_text)
    sample_text = _sample_text(schema_info_or_text, sample_rows)
    table_name = (
        str(schema_info_or_text["table_name"])
        if isinstance(schema_info_or_text, dict)
        else quote_table_name(TABLE_NAME)
    )

    prompt = f"""You are a senior SQL Server analyst for maritime operations.
Write one high-quality SQL Server SELECT query that answers the user's question.

Table boundary:
- There is exactly one allowed table: {table_name}
- Do not use joins, temp tables, table variables, stored procedures, dynamic SQL,
  DDL, DML, EXEC, SELECT INTO, or any table other than {table_name}.

Available columns:
{schema_text}

Sample rows:
{sample_text}

User question:
{question}

Output rules:
- Return ONLY the SQL query, with no markdown and no explanation.
- If the question cannot be answered from these columns, return exactly:
  INSUFFICIENT_COLUMNS
- The query must start with SELECT.
- Always bracket table and column names.
- Use SQL Server syntax: TOP instead of LIMIT, DATEFROMPARTS/EOMONTH when useful,
  and single-quoted ISO dates such as '2026-06-01'.
- For row-listing/detail questions, include TOP {int(row_limit)} unless the user
  explicitly asks for all rows or export/download of all matching rows.
- For aggregate questions, return the aggregate columns and the grouping columns
  needed to answer the question. Every non-aggregated SELECT column must appear
  in GROUP BY.
- Prefer clear aliases such as [TotalFuelConsumption], [RecordCount],
  [AverageSpeed], [LatestEventDate].
- When filtering text from user input, use LIKE '%value%' unless the user asks
  for an exact match. Do not use LIKE on date/datetime columns.
- For a specific month/year, use a half-open date range when a date column exists:
  [DateCol] >= 'YYYY-MM-01' AND [DateCol] < 'YYYY-MM-01 plus one month'.
- "Latest month" or "latest year" means the latest period present in the data
  after applying the same vessel/filter context, not the current calendar period.
- For "highest", "lowest", "latest", or "earliest" where ties are possible, use
  TOP 1 WITH TIES and ORDER BY instead of equality against MAX/MIN.
- For category requests such as consumption, draft, cargo, emissions, distance,
  speed, or weather, scan the full column list and include every relevant column,
  not only the first matching group.
"""

    return _clean_llm_sql(_llm().invoke(prompt).content)


def repair_sql(
    question: str,
    failed_sql: str,
    error_message: str,
    schema_info: dict[str, Any],
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> str:
    """Ask the model for one corrected SELECT after execution or validation fails."""
    prompt = f"""Fix this SQL Server query.

The original user question:
{question}

Allowed table:
{schema_info["table_name"]}

Available columns:
{schema_info["schema_text"]}

Failed query:
{failed_sql}

Error or validation issue:
{error_message}

Return ONLY one corrected SQL Server SELECT query. Use the same safety rules:
single SELECT statement, no joins, no writes, no temp tables, no dynamic SQL, no
tables except {schema_info["table_name"]}. Use TOP {int(row_limit)} for raw
row listings unless the user explicitly requested all rows.
"""
    return _clean_llm_sql(_llm().invoke(prompt).content)


def _strip_sql_comments(sql_query: str) -> str:
    no_block = re.sub(r"/\*.*?\*/", " ", sql_query, flags=re.DOTALL)
    return re.sub(r"--.*?$", " ", no_block, flags=re.MULTILINE).strip()


def _normalized_table_ref(table_ref: str) -> str:
    parts = [part.lower() for part in _identifier_parts(table_ref)]
    return ".".join(parts)


def validate_sql(sql_query: str, table_name: str | None = None) -> tuple[bool, str]:
    """
    Validate that a generated query is a single read-only SELECT against the
    configured table only. This is intentionally conservative.
    """
    if not sql_query or not sql_query.strip():
        return False, "The generated query was empty."

    stripped = _strip_sql_comments(sql_query)
    statements = [part.strip() for part in stripped.split(";") if part.strip()]
    if len(statements) != 1:
        return False, "Only one SQL statement is allowed."

    statement = statements[0]
    if not re.match(r"^\s*SELECT\b", statement, flags=re.IGNORECASE):
        return False, "Only SELECT statements are allowed."

    blocked_patterns = [
        r"\bINSERT\b",
        r"\bUPDATE\b",
        r"\bDELETE\b",
        r"\bMERGE\b",
        r"\bDROP\b",
        r"\bALTER\b",
        r"\bCREATE\b",
        r"\bTRUNCATE\b",
        r"\bEXEC(?:UTE)?\b",
        r"\bGRANT\b",
        r"\bREVOKE\b",
        r"\bBACKUP\b",
        r"\bRESTORE\b",
        r"\bDBCC\b",
        r"\bWAITFOR\b",
        r"\bUSE\b",
        r"\bINTO\b",
        r"\bOPENROWSET\b",
        r"\bOPENDATASOURCE\b",
        r"\bxp_\w+",
        r"\bsp_\w+",
    ]
    for pattern in blocked_patterns:
        if re.search(pattern, statement, flags=re.IGNORECASE):
            return False, f"Blocked unsafe SQL pattern: {pattern}"

    if re.search(r"\bJOIN\b", statement, flags=re.IGNORECASE):
        return False, "Joins are blocked because this assistant is scoped to one table."

    allowed_ref = _normalized_table_ref(table_name or TABLE_NAME)
    table_refs = re.findall(
        r"\bFROM\s+((?:\[[^\]]+\]|[A-Za-z_][\w$#]*)(?:\s*\.\s*(?:\[[^\]]+\]|[A-Za-z_][\w$#]*)){0,2})",
        statement,
        flags=re.IGNORECASE,
    )
    if not table_refs:
        return False, "The query does not reference the configured table."

    for table_ref in table_refs:
        if _normalized_table_ref(table_ref) != allowed_ref:
            return False, f"Query referenced a table outside the allowed table: {table_ref}"

    return True, "OK"


def is_safe_select(sql_query: str, table_name: str | None = None) -> bool:
    """Backward-compatible boolean safety check."""
    return validate_sql(sql_query, table_name)[0]


def run_query(
    conn: pyodbc.Connection,
    sql_query: str,
    table_name: str | None = None,
) -> pd.DataFrame:
    """Execute validated SQL and return a pandas DataFrame of results."""
    is_valid, reason = validate_sql(sql_query, table_name)
    if not is_valid:
        raise ValueError(reason)
    return pd.read_sql(sql_query, conn)


def generate_explanation(question: str, result_df: pd.DataFrame, max_rows_to_show: int = 20) -> str:
    """Generate a short business answer from the result table."""
    total_rows = len(result_df)
    if total_rows == 0:
        return "No matching rows were found for that question."

    sample_df = result_df.head(max_rows_to_show)
    if total_rows > max_rows_to_show:
        data_section = (
            f"(Showing the first {max_rows_to_show} of {total_rows} total rows)\n"
            f"{sample_df.to_string(index=False, max_cols=50, max_colwidth=80)}"
        )
    else:
        data_section = sample_df.to_string(index=False, max_cols=50, max_colwidth=80)

    prompt = f"""You are a maritime operations analyst.
Use the query result to answer the user's question in plain English.

Rules:
- Do not mention SQL, databases, queries, exports, or implementation details.
- Be concise: one short paragraph, or up to three bullets if the result has
  multiple grouped rows.
- If the table contains aggregate values such as counts, totals, averages, min,
  or max, answer from those values. Do not confuse row count with the answer.
- Only state numbers and facts present in the result table.
- If the result is a raw detail listing, summarize what matched and mention the
  number of rows returned.

Rows returned:
{total_rows}

Result table:
{data_section}

User question:
{question}
"""
    return _llm().invoke(prompt).content.strip()


def suggest_questions(schema_info: dict[str, Any]) -> list[str]:
    """Create lightweight example questions from the discovered columns."""
    columns = schema_info["column_names"]
    lowered = {col.lower(): col for col in columns}

    def find_column(*needles: str) -> str | None:
        for needle in needles:
            for lower, original in lowered.items():
                if needle in lower:
                    return original
        return None

    vessel_col = find_column("vessel", "ship")
    date_col = find_column("eventdate", "date", "time")
    consumption_col = find_column("cons", "fuel")
    speed_col = find_column("speed")

    examples = ["How many records are in this table?"]
    if vessel_col and date_col:
        examples.append(f"Show the latest month of records for a vessel using [{vessel_col}].")
    if consumption_col:
        examples.append("Which records have the highest fuel consumption?")
    if speed_col:
        examples.append("What is the average speed by vessel?")
    if date_col:
        examples.append("Show the monthly record count for the latest year in the data.")

    return examples[:5]


def dataframe_profile(result_df: pd.DataFrame) -> dict[str, Any]:
    """Small UI-oriented profile for result metrics and chart choices."""
    numeric_cols = list(result_df.select_dtypes(include="number").columns)
    date_cols = list(result_df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns)
    text_cols = [
        col
        for col in result_df.columns
        if col not in numeric_cols and col not in date_cols
    ]
    return {
        "rows": len(result_df),
        "columns": len(result_df.columns),
        "numeric_columns": numeric_cols,
        "date_columns": date_cols,
        "text_columns": text_cols,
    }
