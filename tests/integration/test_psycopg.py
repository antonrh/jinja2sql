from typing import Iterator

import psycopg
import pytest
from psycopg.conninfo import make_conninfo
from pytest_docker.plugin import Services

from jinja2sql import Jinja2SQL
from jinja2sql._core import ParamStyle


def _psycopg_check_alive(conninfo: str) -> bool:
    try:
        conn = psycopg.connect(conninfo)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
    except psycopg.DatabaseError:
        return False
    return True


@pytest.fixture(scope="module")
def conn(
    docker_services: Services, docker_ip: str, j2sql: Jinja2SQL
) -> Iterator[psycopg.Connection]:
    port = docker_services.port_for("psycopg", 5432)

    assert port == 5432

    conninfo = make_conninfo(
        dbname="jinja2sql",
        user="jinja2sql",
        password="jinja2sql",
        host=docker_ip,
        port=port,
    )

    docker_services.wait_until_responsive(
        timeout=60.0,
        pause=0.5,
        check=lambda: _psycopg_check_alive(conninfo),
    )

    conn = psycopg.connect(conninfo)

    query, _ = j2sql.from_file("postgres/schema.sql")
    conn.execute(query)

    query, _ = j2sql.from_file("postgres/users.sql")
    conn.execute(query)

    try:
        yield conn
    finally:
        conn.close()


@pytest.mark.parametrize("param_style", ["format", "pyformat"])
def test_supported_param_styles(
    j2sql: Jinja2SQL, conn: psycopg.Connection, param_style: ParamStyle
) -> None:
    email = "test@mail.com"

    query, params = j2sql.from_string(
        'SELECT * FROM "public"."user" WHERE email = {{ email }}',
        context={"email": email},
        param_style=param_style,
    )

    cursor = conn.cursor()
    result = cursor.execute(query, params).fetchall()

    assert result
    assert email in result[0]
