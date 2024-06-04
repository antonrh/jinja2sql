from textwrap import dedent


def assert_sql(sql: str, other: str) -> None:
    assert dedent(sql).strip().lower() == dedent(other).strip().lower()
