import pathlib

import jinja2
import pytest

from jinja2sql import Jinja2SQL, identifier
from jinja2sql._core import ParamStyle

from tests.unit.asserts import assert_sql


@pytest.fixture(scope="session")
def sql_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "sql"


@pytest.fixture(scope="session")
def j2sql(sql_path: pathlib.Path) -> Jinja2SQL:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(sql_path))
    return Jinja2SQL(env)


@pytest.fixture(scope="session")
def async_j2sql(sql_path: pathlib.Path) -> Jinja2SQL:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(sql_path), enable_async=True
    )
    return Jinja2SQL(env)


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
        (
            "named",
            """SELECT * FROM table WHERE param1 = :param1__1
            AND param2 = :param2__2""",
        ),
        (
            "pyformat",
            """SELECT * FROM table WHERE param1 = %(param1__1)s
            AND param2 = %(param2__2)s""",
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
    assert params == {"param1__1": param1, "param2__2": param2}


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


def test_bind_inclause_empty_list(j2sql: Jinja2SQL) -> None:
    with pytest.raises(ValueError, match="IN clause cannot be empty"):
        j2sql.from_string(
            "SELECT * FROM table WHERE param IN {{ list_param | inclause }}",
            context={"list_param": []},
            param_style="named",
        )


@pytest.mark.parametrize(
    "param_style, expected_query",
    [
        (
            "named",
            """
            SELECT * FROM table WHERE param IN (:list_param__in__1, :list_param__in__2)
            """,
        ),
        (
            "pyformat",
            """
            SELECT * FROM table
            WHERE param IN (%(list_param__in__1)s, %(list_param__in__2)s)
            """,
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
    assert params == {"list_param__in__1": value1, "list_param__in__2": value2}


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
    param = "value"

    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param1 = {{ param }}",
        param_style=lambda key, index: f"{{{key}}}",
        context={"param": param},
    )

    assert_sql(query, "SELECT * FROM table WHERE param1 = {param__1}")
    assert params == {"param__1": param}


def test_bind_in_loop(j2sql: Jinja2SQL) -> None:
    query, params = j2sql.from_string(
        """SELECT * FROM table WHERE TRUE
        {%- for param in params %}
        {%- if loop.first %} AND {% else %} OR {% endif %}param = {{ param }}
        {%- endfor -%}
        """,
        param_style="named",
        context={"params": ["one", "two"]},
    )

    assert_sql(
        query,
        """
        SELECT * FROM table WHERE TRUE AND param = :param__1 OR param = :param__2""",
    )
    assert params == {"param__1": "one", "param__2": "two"}


def test_identifier(j2sql: Jinja2SQL) -> None:
    query, params = j2sql.from_string(
        "SELECT * FROM {{ table | identifier }}",
        context={"table": "user"},
        param_style="numeric",
    )

    assert_sql(query, "SELECT * FROM user")
    assert params == []


@pytest.mark.parametrize(
    "param_style, expected_query, expected_params",
    [
        (
            "named",
            "SELECT * FROM table WHERE p1 = :p1__1 AND p2 = :p2__2",
            {"p1__1": "v1", "p2__2": "v2"},
        ),
        (
            "qmark",
            "SELECT * FROM table WHERE p1 = ? AND p2 = ?",
            ["v1", "v2"],
        ),
        (
            "asyncpg",
            "SELECT * FROM table WHERE p1 = $1 AND p2 = $2",
            ["v1", "v2"],
        ),
    ],
)
def test_explicit_bind(
    j2sql: Jinja2SQL,
    param_style: ParamStyle,
    expected_query: str,
    expected_params: dict[str, str] | list[str],
) -> None:
    query, params = j2sql.from_string(
        "SELECT * FROM table"
        " WHERE p1 = {{ p1 | bind('p1') }}"
        " AND p2 = {{ p2 | bind('p2') }}",
        context={"p1": "v1", "p2": "v2"},
        param_style=param_style,
    )

    assert_sql(query, expected_query)
    assert params == expected_params


def test_explicit_bind_in(j2sql: Jinja2SQL) -> None:
    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param IN {{ items | inclause('items') }}",
        context={"items": ["a", "b"]},
        param_style="named",
    )

    assert_sql(
        query,
        "SELECT * FROM table WHERE param IN (:items__in__1, :items__in__2)",
    )
    assert params == {"items__in__1": "a", "items__in__2": "b"}


def test_explicit_identifier(j2sql: Jinja2SQL) -> None:
    query, params = j2sql.from_string(
        "SELECT * FROM {{ table | identifier }}",
        context={"table": "users"},
        param_style="named",
        identifier_quote_char='"',
    )

    assert_sql(query, 'SELECT * FROM "users"')
    assert params == {}


def test_explicit_bind_with_other_filters(j2sql: Jinja2SQL) -> None:
    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param = {{ param | upper | bind('param') }}",
        context={"param": "value"},
        param_style="named",
    )

    assert_sql(query, "SELECT * FROM table WHERE param = :param__1")
    assert params == {"param__1": "VALUE"}


def test_autobind_false() -> None:
    j2sql = Jinja2SQL(autobind=False)

    query, params = j2sql.from_string(
        "SELECT * FROM {{ table | identifier }}"
        " WHERE p1 = {{ p1 | bind('p1') }}"
        " AND p2 = {{ p2 | bind('p2') }}",
        context={"table": "users", "p1": "v1", "p2": "v2"},
        param_style="named",
    )

    assert_sql(query, "SELECT * FROM users WHERE p1 = :p1__1 AND p2 = :p2__2")
    assert params == {"p1__1": "v1", "p2__2": "v2"}


def test_autobind_false_inclause() -> None:
    j2sql = Jinja2SQL(autobind=False)

    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param IN {{ items | inclause('items') }}",
        context={"items": ["a", "b"]},
        param_style="named",
    )

    assert_sql(
        query,
        "SELECT * FROM table WHERE param IN (:items__in__1, :items__in__2)",
    )
    assert params == {"items__in__1": "a", "items__in__2": "b"}


def test_autobind_false_no_bind_renders_raw() -> None:
    j2sql = Jinja2SQL(autobind=False)

    query, params = j2sql.from_string(
        "SELECT * FROM table WHERE param = {{ param }}",
        context={"param": "value"},
        param_style="named",
    )

    assert_sql(query, "SELECT * FROM table WHERE param = value")
    assert params == {}


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


def test_register_filter() -> None:
    j2sql = Jinja2SQL()
    j2sql.register_filter("custom_filter", lambda value: f"{value}_with_filter")

    query, params = j2sql.from_string(
        """SELECT * FROM table WHERE param = {{ param | custom_filter }}""",
        context={
            "param": "value",
        },
    )

    assert_sql(query, "SELECT * FROM table WHERE param = :param__1")
    assert params == {"param__1": "value_with_filter"}


def test_register_filter_with_bind() -> None:
    j2sql = Jinja2SQL()

    def array_filter(j2sql: Jinja2SQL, value: list[str]) -> str:
        parts = ", ".join(f"'{item}'" for item in value)
        return identifier(j2sql, parts)

    j2sql.register_filter("array", array_filter, bind=True)

    query, params = j2sql.from_string(
        """SELECT ARRAY[{{ param | array }}] AS array""",
        context={
            "param": ["0", "1"],
        },
    )

    assert_sql(query, "SELECT ARRAY['0', '1'] AS array")
    assert params == {}


def test_filter_decorator() -> None:
    j2sql = Jinja2SQL()

    @j2sql.filter
    def custom_filter2(value: str) -> str:
        return f"{value}_with_decorator"

    query, params = j2sql.from_string(
        """SELECT * FROM table WHERE param = {{ param | custom_filter2 }}""",
        context={
            "param": "value",
        },
    )

    assert_sql(query, "SELECT * FROM table WHERE param = :param__1")
    assert params == {"param__1": "value_with_decorator"}


def test_filter_decorator_with_bind() -> None:
    j2sql = Jinja2SQL()

    @j2sql.filter(name="array2", bind=True)
    def array_filter(j2sql: Jinja2SQL, value: list[str]) -> str:
        parts = ", ".join(f"'{item}'" for item in value)
        return identifier(j2sql, parts)

    query, params = j2sql.from_string(
        """SELECT ARRAY[{{ param | array2 }}] AS array""",
        context={
            "param": ["0", "1"],
        },
    )

    assert_sql(query, "SELECT ARRAY['0', '1'] AS array")
    assert params == {}
