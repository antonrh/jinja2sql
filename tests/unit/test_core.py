import pathlib
from typing import List

import pytest

from jinja2sql import Jinja2SQL
from jinja2sql._core import ParamStyle

from tests.unit.asserts import assert_sql


@pytest.fixture(scope="session")
def sql_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "sql"


@pytest.fixture(scope="session")
def j2sql(sql_path: pathlib.Path) -> Jinja2SQL:
    return Jinja2SQL(searchpath=sql_path)


@pytest.fixture(scope="session")
def async_j2sql(sql_path: pathlib.Path) -> Jinja2SQL:
    return Jinja2SQL(searchpath=sql_path, enable_async=True)


@pytest.mark.parametrize(
    "param_style, expected_query",
    [
        ("qmark", "SELECT * FROM table WHERE param1 = ? AND param2 = ?"),
        ("format", "SELECT * FROM table WHERE param1 = %s AND param2 = %s"),
        ("numeric", "SELECT * FROM table WHERE param1 = :1 AND param2 = :2"),
        ("asyncpg", "SELECT * FROM table WHERE param1 = $1 AND param2 = $2"),
    ],
)
def test_bind_params_with_positional_param_style(
    j2sql: Jinja2SQL, param_style: ParamStyle, expected_query: str
) -> None:
    param1 = "value1"
    param2 = "value2"

    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param1 = {{ param1 }} AND param2 = {{ param2 }}",
        context={"param1": param1, "param2": param2},
        param_style=param_style,
    )

    assert_sql(query, expected_query)
    assert params == [param1, param2]


@pytest.mark.parametrize(
    "param_style, expected_query",
    [
        ("named", "SELECT * FROM table WHERE param1 = :param1 AND param2 = :param2"),
        (
            "pyformat",
            "SELECT * FROM table WHERE param1 = %(param1)s AND param2 = %(param2)s",
        ),
    ],
)
def test_bind_params_with_keyword_param_style(
    j2sql: Jinja2SQL, param_style: ParamStyle, expected_query: str
) -> None:
    param1 = "value1"
    param2 = "value2"

    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param1 = {{ param1 }} AND param2 = {{ param2 }}",
        context={"param1": param1, "param2": param2},
        param_style=param_style,
    )

    assert_sql(query, expected_query)
    assert params == {"param1": param1, "param2": param2}


@pytest.mark.parametrize(
    "param_style, expected_query",
    [
        ("qmark", "SELECT * FROM table WHERE param IN (?, ?)"),
        ("format", "SELECT * FROM table WHERE param IN (%s, %s)"),
        ("numeric", "SELECT * FROM table WHERE param IN (:1, :2)"),
        ("asyncpg", "SELECT * FROM table WHERE param IN ($1, $2)"),
    ],
)
def test_bind_inclause_params_with_positional_param_style(
    j2sql: Jinja2SQL, param_style: ParamStyle, expected_query: str
) -> None:
    value1 = "value1"
    value2 = "value2"

    list_param = [value1, value2]

    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param IN {{ list_param | inclause }}",
        context={"list_param": list_param},
        param_style=param_style,
    )

    assert_sql(query, expected_query)
    assert params == [value1, value2]


@pytest.mark.parametrize(
    "param_style, expected_query",
    [
        ("named", "SELECT * FROM table WHERE param IN (:list_param_1, :list_param_2)"),
        (
            "pyformat",
            "SELECT * FROM table WHERE param IN (%(list_param_1)s, %(list_param_2)s)",
        ),
    ],
)
def test_bind_inclause_params_with_keyword_param_style(
    j2sql: Jinja2SQL, param_style: ParamStyle, expected_query: str
) -> None:
    value1 = "value1"
    value2 = "value2"

    list_param = [value1, value2]

    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param IN {{ list_param | inclause }}",
        context={"list_param": list_param},
        param_style=param_style,
    )

    assert_sql(query, expected_query)
    assert params == {"list_param_1": value1, "list_param_2": value2}


def test_bind_same_params_with_positional_param_style(j2sql: Jinja2SQL) -> None:
    user = "user@example.com"

    query, params = j2sql.from_string(
        "SELECT * FROM users WHERE username = {{ user }} OR email = {{ user }}",
        context={"user": user},
        param_style="format",
    )

    assert_sql(query, "SELECT * FROM users WHERE username = %s OR email = %s")
    assert params == [user, user]


def test_bind_custom_param_style(j2sql: Jinja2SQL) -> None:
    param1 = "value1"

    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param1 = {{ param1 }}",
        param_style=lambda key, index: f"{{{key}}}",
        context={"param1": param1},
    )

    assert_sql(query, "SELECT * FROM table WHERE param1 = {param1}")
    assert params == {"param1": param1}


def test_identifier(j2sql: Jinja2SQL) -> None:
    query, params = j2sql.from_string(
        "SELECT * FROM {{ table | identifier }}",
        context={"table": "user"},
        param_style="numeric",
    )

    assert_sql(query, "SELECT * FROM user")
    assert params == []


def test_safe_sql(j2sql: Jinja2SQL) -> None:
    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param = '{{ param | safe }}'",
        context={"param": "value"},
        param_style="numeric",
    )

    assert_sql(query, "SELECT * FROM table WHERE param = 'value'")
    assert params == []


def test_from_file(j2sql: Jinja2SQL) -> None:
    param1 = "value1"
    param2 = "value2"

    query, params = j2sql.from_file(
        "query1.sql",
        context={
            "param1": param1,
            "param2": param2,
        },
        param_style="numeric",
    )

    assert_sql(query, "SELECT * FROM table WHERE param1 = :1 AND param2 = :2")
    assert params == [param1, param2]


@pytest.mark.asyncio
async def test_from_string_async(async_j2sql: Jinja2SQL) -> None:
    param1 = "value1"

    query, params = await async_j2sql.from_string_async(
        "SELECT * FROM table WHERE param1 = {{ param1 }}",
        context={
            "param1": param1,
        },
        param_style="numeric",
    )

    assert_sql(query, "SELECT * FROM table WHERE param1 = :1")
    assert params == [param1]


@pytest.mark.asyncio
async def test_from_file_async(async_j2sql: Jinja2SQL) -> None:
    param1 = "value1"
    param2 = "value2"

    query, params = await async_j2sql.from_file_async(
        "query1.sql",
        context={
            "param1": param1,
            "param2": param2,
        },
        param_style="numeric",
    )

    assert_sql(query, "SELECT * FROM table WHERE param1 = :1 AND param2 = :2")
    assert params == [param1, param2]


def test_register_filter(j2sql: Jinja2SQL) -> None:
    j2sql.register_filter("custom_filter", lambda value: f"{value}_with_filter")

    query, params = j2sql.from_string(
        """SELECT * FROM table WHERE param = {{ param | custom_filter }}""",
        context={
            "param": "value",
        },
    )

    assert_sql(query, "SELECT * FROM table WHERE param = :param")
    assert params == {"param": "value_with_filter"}


def test_register_filter_with_self(j2sql: Jinja2SQL) -> None:
    def array_filter(j2sql: Jinja2SQL, value: List[str]) -> str:
        return j2sql.identifier(", ".join(f"'{item}'" for item in value))

    j2sql.register_filter("array", array_filter)

    query, params = j2sql.from_string(
        """SELECT ARRAY[{{ param | array }}] AS array""",
        context={
            "param": ["0", "1"],
        },
    )

    assert_sql(query, "SELECT ARRAY['0', '1'] AS array")
    assert params == {}


def test_filter_decorator(j2sql: Jinja2SQL) -> None:
    @j2sql.filter
    def custom_filter2(value: str) -> str:
        return f"{value}_with_decorator"

    query, params = j2sql.from_string(
        """SELECT * FROM table WHERE param = {{ param | custom_filter2 }}""",
        context={
            "param": "value",
        },
    )

    assert_sql(query, "SELECT * FROM table WHERE param = :param")
    assert params == {"param": "value_with_decorator"}


def test_filter_decorator_with_self(j2sql: Jinja2SQL) -> None:
    @j2sql.filter(name="array2")
    def array_filter(self: Jinja2SQL, value: List[str]) -> str:
        return self.identifier(", ".join(f"'{item}'" for item in value))

    query, params = j2sql.from_string(
        """SELECT ARRAY[{{ param | array2 }}] AS array""",
        context={
            "param": ["0", "1"],
        },
    )

    assert_sql(query, "SELECT ARRAY['0', '1'] AS array")
    assert params == {}
