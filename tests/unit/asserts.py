import re
from textwrap import dedent


def assert_sql(sql: str, other: str) -> None:
    assert _normalize_sql(sql) == _normalize_sql(other), "SQL strings do not match"


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", dedent(sql).strip().lower())
