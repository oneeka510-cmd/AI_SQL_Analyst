def validate_sql(query):

    query_upper = query.strip().upper()

    if not query_upper.startswith("SELECT"):
        raise ValueError(
            "Only SELECT statements allowed."
        )

    forbidden = {
        "DELETE",
        "UPDATE",
        "INSERT",
        "DROP",
        "ALTER",
        "TRUNCATE"
    }

    for keyword in forbidden:
        if keyword in query_upper:
            raise ValueError(
                f"{keyword} not allowed."
            )

    return True