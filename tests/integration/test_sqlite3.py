import sqlite3
from typing import Iterator

import pytest

from jinja2sql import Jinja2SQL
from jinja2sql.core import ParamStyle


@pytest.fixture(scope="session")
def conn(j2sql: Jinja2SQL) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")

    query, _ = j2sql.from_file("sqlite/schema.sql")
    conn.execute(query)

    query, _ = j2sql.from_file("sqlite/users.sql")
    conn.execute(query)

    yield conn

    conn.close()


@pytest.mark.parametrize("param_style", ["named", "qmark", "numeric"])
def test_supported_param_styles(
    j2sql: Jinja2SQL, conn: sqlite3.Connection, param_style: ParamStyle
) -> None:
    email = "test@mail.com"

    query, params = j2sql.from_string(
        "SELECT * FROM user WHERE email = {{ email }}",
        context={"email": email},
        param_style=param_style,
    )

    cursor = conn.cursor()
    result = cursor.execute(query, params).fetchall()

    assert result
    assert email in result[0]
