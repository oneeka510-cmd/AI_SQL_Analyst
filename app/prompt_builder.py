def build_sql_prompt(
    table_name,
    dtype_info,
    sample_rows,
    user_question
):

    domain_name= "maritime"

    return f"""
You are a {domain_name} domain expert.

Generate a SQL Server query from the user question.

# Table Name
{table_name}

# Columns and Data Types
{dtype_info}

# Sample Rows
{sample_rows}

# User Question
{user_question}

Rules:

- Return ONLY the SQL query.
- Use SQL Server syntax.
- Never use LIMIT.
- Use TOP when needed.
- Use exact column names provided.
- Do not invent columns.
- When user asks for totals, use SUM().
- When filtering names, use LIKE with wildcards.

SQL Server Rules:

1. Every non-aggregated column in a SELECT with aggregates must appear in GROUP BY.
2. Do not mix MAX(), MIN(), SUM(), AVG(), COUNT() with regular columns unless GROUP BY is used.
3. For latest or earliest records, prefer TOP 1 with ORDER BY.
"""