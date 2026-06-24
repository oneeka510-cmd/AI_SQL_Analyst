import warnings
from app.validator import validate_sql
from app.config import TABLE_NAME
from app.llm import (
    generate_sql,
    explain_result
)
from app.database import (
    get_connection,
    get_table_context,
    execute_query
)

from app.prompt_builder import (
    build_sql_prompt
)



warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy"
)


def main():

    conn = get_connection()

    dtype_info, sample_rows = get_table_context(
        conn,
        TABLE_NAME
    )
    conn.close()
    
    user_question = input(
        "Enter your question: "
    )

    prompt = build_sql_prompt(
        TABLE_NAME,
        dtype_info,
        sample_rows,
        user_question
    )

    sql_query = generate_sql(prompt)

    print("\nGenerated SQL:\n")
    print(sql_query)
    try:
        validate_sql(sql_query)

        result_df = execute_query(
            sql_query
        )

        print("\nQuery Result:\n")
        print(result_df)

        answer = explain_result(
            user_question,
            sql_query,
            result_df
        )

        print("\nAnswer:\n")
        print(answer)
        print("\n")

    except Exception as e:

        print("\nExecution Error:")
        print(e)

if __name__ == "__main__":
    main()
    