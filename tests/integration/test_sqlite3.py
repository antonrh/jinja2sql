import sqlite3
from typing import Iterator

import pytest

from jinjaq import JinjaQ
from jinjaq.core import ParamStyle


@pytest.fixture(scope="session")
def conn(jq: JinjaQ) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")

    query, _ = jq.from_file("sqlite/schema.sql")
    conn.execute(query)

    query, _ = jq.from_file("sqlite/users.sql")
    conn.execute(query)

    yield conn

    conn.close()


@pytest.mark.parametrize("param_style", ["named", "qmark", "numeric"])
def test_supported_param_styles(
    jq: JinjaQ, conn: sqlite3.Connection, param_style: ParamStyle
) -> None:
    email = "test@mail.com"

    query, params = jq.from_string(
        "SELECT * FROM user WHERE email = {{ email }}",
        params={"email": email},
        param_style=param_style,
    )

    cursor = conn.cursor()
    result = cursor.execute(query, params).fetchall()

    assert result
    assert email in result[0]
