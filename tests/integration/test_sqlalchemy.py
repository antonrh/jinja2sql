from typing import Iterator

import pytest
import sqlalchemy as sa

from jinja2sql import Jinja2SQL
from jinja2sql.core import ParamStyle


@pytest.fixture(scope="module")
def conn(j2sql: Jinja2SQL) -> Iterator[sa.Connection]:
    engine = sa.create_engine("sqlite:///:memory:")

    with engine.connect() as conn:
        query, _ = j2sql.from_file("sqlite/schema.sql")
        conn.execute(sa.text(query))

        query, _ = j2sql.from_file("sqlite/users.sql")
        conn.execute(sa.text(query))

        yield conn


@pytest.mark.parametrize("param_style", ["named"])
def test_supported_param_styles(
    j2sql: Jinja2SQL, conn: sa.Connection, param_style: ParamStyle
) -> None:
    email = "test@mail.com"

    query, params = j2sql.from_string(
        "SELECT * FROM user WHERE email = {{ email }}",
        context={"email": email},
        param_style=param_style,
    )

    result = conn.execute(sa.text(query).bindparams(**params)).fetchall()

    assert result
    assert email in result[0]
