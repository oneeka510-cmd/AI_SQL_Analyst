"""
Streamlit frontend for the single-table SQL assistant.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from db_utils import (
    DB_DATABASE,
    DEFAULT_ROW_LIMIT,
    TABLE_NAME,
    dataframe_profile,
    generate_explanation,
    generate_sql,
    get_connection,
    get_schema_info,
    repair_sql,
    run_query,
    suggest_questions,
    validate_sql,
)


st.set_page_config(
    page_title="SQL AI Analyst",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.2rem; }
    [data-testid="stMetricValue"] { font-size: 1.45rem; }
    .small-muted { color: #667085; font-size: 0.88rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Reading table schema...")
def load_schema(database_name: str, table_name: str) -> dict:
    conn = get_connection(database_name)
    try:
        return get_schema_info(conn, table_name=table_name)
    finally:
        conn.close()


def init_state() -> None:
    defaults = {
        "result_df": None,
        "explanation": None,
        "sql_query": None,
        "question": "",
        "history": [],
        "query_error": None,
        "used_repair": False,
        "active_database": None,
        "active_table": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def set_question(text: str) -> None:
    st.session_state.question = text


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")
    buffer.seek(0)
    return buffer.getvalue()


def render_result_metrics(df: pd.DataFrame) -> None:
    profile = dataframe_profile(df)
    metric_cols = st.columns(4)
    metric_cols[0].metric("Rows", f"{profile['rows']:,}")
    metric_cols[1].metric("Columns", f"{profile['columns']:,}")
    metric_cols[2].metric("Numeric fields", f"{len(profile['numeric_columns']):,}")
    metric_cols[3].metric(
        "Text/date fields",
        f"{len(profile['text_columns']) + len(profile['date_columns']):,}",
    )


def render_quick_chart(df: pd.DataFrame) -> None:
    profile = dataframe_profile(df)
    numeric_cols = profile["numeric_columns"]
    label_cols = profile["text_columns"] + profile["date_columns"]

    if df.empty or not numeric_cols:
        st.info("No numeric column is available for a quick chart.")
        return

    chart_col, value_col = st.columns([1, 1])
    x_col = chart_col.selectbox("Label column", ["Row number"] + label_cols)
    y_col = value_col.selectbox("Value column", numeric_cols)

    chart_df = df.head(100).copy()
    if x_col == "Row number":
        chart_df.index = range(1, len(chart_df) + 1)
        st.bar_chart(chart_df[y_col])
    else:
        chart_df[x_col] = chart_df[x_col].astype(str)
        st.bar_chart(chart_df.set_index(x_col)[y_col])


init_state()

with st.sidebar:
    st.header("Workspace")
    st.caption("Single-table SQL Server assistant")
    selected_database = st.text_input(
        "Database",
        value=DB_DATABASE or "",
        help="Defaults to DB_DATABASE from .env. Change this to connect to another database on the same server.",
    ).strip()
    selected_table = st.text_input(
        "Table",
        value=TABLE_NAME,
        help="Use schema-qualified SQL Server format, for example [dbo].[MyTable].",
    ).strip()

if (
    st.session_state.active_database != selected_database
    or st.session_state.active_table != selected_table
):
    st.session_state.result_df = None
    st.session_state.explanation = None
    st.session_state.sql_query = None
    st.session_state.query_error = None
    st.session_state.used_repair = False
    st.session_state.history = []
    st.session_state.active_database = selected_database
    st.session_state.active_table = selected_table

if not selected_database or not selected_table:
    st.error("Enter both a database name and a table name to connect.")
    st.stop()

try:
    schema_info = load_schema(selected_database, selected_table)
except Exception as exc:
    st.error(f"Could not connect to the selected table: {exc}")
    st.stop()


with st.sidebar:
    st.divider()
    st.metric("Connected database", selected_database)
    st.metric("Connected table", schema_info["table_name"])
    st.metric("Columns", len(schema_info["columns"]))

    if st.button("Refresh schema"):
        load_schema.clear()
        st.rerun()

    st.divider()
    st.subheader("Schema")
    schema_df = pd.DataFrame(
        {
            "Column": [col.name for col in schema_info["columns"]],
            "Type": [col.type_label for col in schema_info["columns"]],
            "Nullable": ["Yes" if col.nullable else "No" for col in schema_info["columns"]],
        }
    )
    st.dataframe(schema_df, use_container_width=True, hide_index=True, height=260)

    with st.expander("Sample rows"):
        st.dataframe(schema_info["sample_df"], use_container_width=True, hide_index=True)


st.title("SQL AI Analyst")
st.caption(
    f"Ask questions against `{schema_info['table_name']}` in database `{selected_database}`."
)

examples = suggest_questions(schema_info)
example_cols = st.columns(len(examples))
for idx, example in enumerate(examples):
    example_cols[idx].button(
        example,
        on_click=set_question,
        args=(example,),
        use_container_width=True,
    )

with st.form("ask_form", clear_on_submit=False):
    question = st.text_area(
        "Question",
        key="question",
        height=110,
        placeholder="Example: Show total fuel consumption by vessel for the latest month in the data.",
    )

    settings_col, action_col = st.columns([2, 1])
    row_limit = settings_col.slider(
        "Default row cap for detail queries",
        min_value=50,
        max_value=10000,
        value=min(max(DEFAULT_ROW_LIMIT, 50), 10000),
        step=50,
        help="The model uses this cap for broad detail/listing requests unless you explicitly ask for all rows.",
    )
    show_debug = settings_col.toggle("Show generated SQL by default", value=False)
    submitted = action_col.form_submit_button(
        "Run analysis",
        type="primary",
        use_container_width=True,
    )


if submitted:
    clean_question = question.strip()
    if not clean_question:
        st.warning("Enter a question first.")
    else:
        st.session_state.query_error = None
        st.session_state.used_repair = False
        st.session_state.result_df = None
        st.session_state.explanation = None
        st.session_state.sql_query = None

        with st.status("Generating and running a safe query...", expanded=True) as status:
            st.write("Building SQL from the connected table schema.")
            sql_query = generate_sql(clean_question, schema_info, row_limit=row_limit)

            if sql_query == "INSUFFICIENT_COLUMNS":
                st.session_state.query_error = (
                    "The connected table does not appear to contain the columns needed for that question."
                )
                status.update(label="Question cannot be answered from this table.", state="error")
            else:
                is_valid, validation_reason = validate_sql(sql_query, selected_table)
                if not is_valid:
                    st.write("Initial SQL failed validation. Asking for one corrected query.")
                    sql_query = repair_sql(
                        clean_question,
                        sql_query,
                        validation_reason,
                        schema_info,
                        row_limit=row_limit,
                    )
                    st.session_state.used_repair = True
                    is_valid, validation_reason = validate_sql(sql_query, selected_table)

                if not is_valid:
                    st.session_state.query_error = validation_reason
                    status.update(label="Generated SQL was blocked.", state="error")
                else:
                    st.write("Running the validated query.")
                    conn = get_connection(selected_database)
                    try:
                        result_df = run_query(conn, sql_query, selected_table)
                    except Exception as exc:
                        st.write("Execution failed. Asking for one corrected query.")
                        repaired_sql = repair_sql(
                            clean_question,
                            sql_query,
                            str(exc),
                            schema_info,
                            row_limit=row_limit,
                        )
                        is_valid, validation_reason = validate_sql(repaired_sql, selected_table)
                        if not is_valid:
                            raise ValueError(validation_reason) from exc
                        result_df = run_query(conn, repaired_sql, selected_table)
                        sql_query = repaired_sql
                        st.session_state.used_repair = True
                    finally:
                        conn.close()

                    st.write("Summarizing the result.")
                    explanation = generate_explanation(clean_question, result_df)
                    st.session_state.result_df = result_df
                    st.session_state.explanation = explanation
                    st.session_state.sql_query = sql_query
                    st.session_state.history.insert(
                        0,
                        {
                            "question": clean_question,
                            "database": selected_database,
                            "table": schema_info["table_name"],
                            "sql": sql_query,
                            "rows": len(result_df),
                        },
                    )
                    st.session_state.history = st.session_state.history[:8]
                    status.update(label="Analysis complete.", state="complete", expanded=False)


if st.session_state.query_error:
    st.error(st.session_state.query_error)

if st.session_state.explanation:
    st.subheader("Answer")
    st.write(st.session_state.explanation)
    if st.session_state.used_repair:
        st.caption(
            "A corrected query was used after the first generated query failed validation or execution."
        )


if st.session_state.result_df is not None:
    result_df = st.session_state.result_df
    render_result_metrics(result_df)

    data_tab, chart_tab, sql_tab, export_tab, history_tab = st.tabs(
        ["Data", "Chart", "SQL", "Export", "History"]
    )

    with data_tab:
        st.dataframe(result_df, use_container_width=True, hide_index=True)

    with chart_tab:
        render_quick_chart(result_df)

    with sql_tab:
        if show_debug:
            st.code(st.session_state.sql_query, language="sql")
        else:
            with st.expander("Show generated SQL"):
                st.code(st.session_state.sql_query, language="sql")

    with export_tab:
        csv_bytes = result_df.to_csv(index=False).encode("utf-8")
        excel_bytes = to_excel_bytes(result_df)
        export_cols = st.columns(2)
        export_cols[0].download_button(
            "Download CSV",
            data=csv_bytes,
            file_name="query_results.csv",
            mime="text/csv",
            use_container_width=True,
        )
        export_cols[1].download_button(
            "Download Excel",
            data=excel_bytes,
            file_name="query_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with history_tab:
        if not st.session_state.history:
            st.info("No completed questions yet.")
        for item in st.session_state.history:
            with st.expander(f"{item['question']} ({item['rows']:,} rows)"):
                st.code(item["sql"], language="sql")
else:
    st.info("Ask a question to generate SQL, run it safely, and inspect the result.")
