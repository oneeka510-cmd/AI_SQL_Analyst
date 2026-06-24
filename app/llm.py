from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def generate_sql(prompt):
    llm= ChatOpenAI()
    response = llm.invoke(prompt)

    sql_query = (
        response.content
        .replace("```sql", "")
        .replace("```", "")
        .strip()
    )

    return sql_query


def explain_result(
    question,
    sql_query,
    result_df
):
    llm=ChatOpenAI()

    prompt = f"""
You are a helpful maritime data analyst.

User Question:
{question}

SQL Query:
{sql_query}

Query Result:
{result_df.to_string(index=False)}

Instructions:
- Answer the user's question using the query result.
- Be concise.
- Do not mention SQL or the table name unless necessary.
- If the result is empty, say no matching records were found.
"""

    response = llm.invoke(prompt)

    return response.content