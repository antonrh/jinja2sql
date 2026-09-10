# Usage

`Jinja2SQL` provides a `jinja2sql.Jinja2SQL` class that can be used to generate SQL queries from string or file templates.

## String Templates

To generate SQL queries from string templates, use the `from_string` method:

```python
from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL()  # default param_style is "named"

query, params = j2sql.from_string(
    "SELECT * FROM {{ table | identifier }} WHERE email = {{ email }}",
    context={"table": "users", "email": "user@mail.com"},
)


assert query == "SELECT * FROM users WHERE email = :email"
assert params == {"email": "user@mail.com"}
```

## File Templates

To generate SQL queries from file templates, use the `from_file` method:

***query.sql***

```sql
SELECT * FROM {{ table | identifier }} WHERE email = {{ email }}
```

***main.py***

```python
from pathlib import Path

import jinja2

from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL(
    jinja2.Environment(loader=jinja2.FileSystemLoader(Path(__name__).parent))
)

query, params = j2sql.from_file(
    "query.sql",
    context={"table": "users", "email": "user@mail.com"},
)

assert query == "SELECT * FROM users WHERE email = :email"
assert params == {"email": "user@mail.com"}
```

## Param Styles

`Jinja2SQL` supports different param styles depending on the database driver you are using.

You can choose between the following supported param styles:

```python
from jinja2sql import Jinja2SQL


j2sql = Jinja2SQL(param_style="named")  # default

query, params = j2sql.from_string(
    "SELECT * FROM table WHERE param = {{ param }}",
    context={"param": ...},
    param_style="named",  # or "qmark", "numeric", "format", "pyformat", "asyncpg"
)
```

| param_style   | Example     |
| ------------- | ----------- |
| `named`       | `:param`    |
| `qmark`       | `?`         |
| `numeric`     | `:1`        |
| `format`      | `%s`        |
| `pyformat`    | `%(param)s` |
| `asyncpg`     | `$1`        |


or you can provide a custom function to format your database specific param style:


```python
from jinja2sql import Jinja2SQL


j2sql = Jinja2SQL()

query, params = j2sql.from_string(
    "SELECT * FROM table WHERE column = {{ param }}",
    context={"param": ...},
    param_style=lambda key, _: f"{{{key}}}",
)

assert query == "SELECT * FROM table WHERE column = {email}"
```


## Async support

`Jinja2SQL` supports asynchronous query generation. Pass a Jinja2 environment with `enable_async=True`:

```python
import jinja2

from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL(jinja2.Environment(enable_async=True))
```

### String Templates

To generate SQL queries from string templates, use the `from_string_async` method:

```python
import asyncio

import jinja2

from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL(jinja2.Environment(enable_async=True))


async def main() -> None:
    query, params = await j2sql.from_string_async(
        "SELECT * FROM {{ table | identifier }} WHERE email = {{ email }}",
        context={"table": "users", "email": "user@mail.com"},
    )

    assert query == "SELECT * FROM users WHERE email = :email"
    assert params == {"email": "user@mail.com"}


asyncio.run(main())
```


### File Templates

To generate SQL queries from file templates, use the `from_file_async` method:

***query.sql***

```sql
SELECT * FROM {{ table | identifier }} WHERE email = {{ email }}
```

***main.py***

```python
import asyncio
from pathlib import Path

import jinja2

from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL(
    jinja2.Environment(
        loader=jinja2.FileSystemLoader(Path(__name__).parent),
        enable_async=True,
    )
)


async def main() -> None:
    query, params = await j2sql.from_file_async(
        "query.sql",
        context={"table": "users", "email": "user@mail.com"},
    )

    assert query == "SELECT * FROM users WHERE email = :email"
    assert params == {"email": "user@mail.com"}


asyncio.run(main())
```

## Manual binding with `autobind=False`

By default, `Jinja2SQL` automatically parameterizes all template variables. If you prefer explicit control, disable auto-binding:

```python
from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL(autobind=False)

query, params = j2sql.from_string(
    "SELECT * FROM {{ table | identifier }}"
    " WHERE email = {{ email | bind('email') }}"
    " AND status IN {{ statuses | inclause('statuses') }}",
    context={
        "table": "users",
        "email": "user@mail.com",
        "statuses": ["active", "pending"],
    },
)

assert query == (
    'SELECT * FROM users'
    ' WHERE email = :email__1'
    ' AND status IN (:statuses__in__2, :statuses__in__3)'
)
```

With `autobind=False`, variables without an explicit `bind` or `_bind_in` filter are rendered as plain text — no parameterization is applied.

## Raw SQL with `safe`

By default, all template variables are automatically parameterized to prevent SQL injection.
The Jinja2 built-in `safe` filter bypasses this behavior and inserts the value directly into the query **without parameterization**:

```python
from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL()

query, params = j2sql.from_string(
    "SELECT * FROM users ORDER BY {{ column | safe }} {{ direction | safe }}",
    context={"column": "created_at", "direction": "DESC"},
)

assert query == "SELECT * FROM users ORDER BY created_at DESC"
assert params == {}
```

!!! warning

    **Never use `safe` with untrusted user input.** Values passed through `safe` are inserted into SQL as-is, which can lead to SQL injection. Use it only for values that you fully control in your code.

    For dynamic table or column names, prefer the `identifier` filter instead — it provides proper escaping.

## Custom filters

`Jinja2SQL` supports custom filters to extend the functionality of the Jinja2 templating engine.

To add custom filters, use the `register_filter` method or `@filter` decorator:

```python
from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL()


@j2sql.filter
def lowercase(value: str) -> str:
    return value.lower()


# or using register_filter
j2sql.register_filter("lowercase", lambda value: value.lower())
```

A filter like that returns a value, and `Jinja2SQL` binds what it returns.

For a filter that writes SQL rather than a value, an operator carrying values of its own, pass `bind=True`. It is then called with the `Binder` of the render as its first argument:

```python
from datetime import date

from markupsafe import Markup

from jinja2sql import Binder, Jinja2SQL

j2sql = Jinja2SQL()


def in_span(binder: Binder, span: tuple[date, date]) -> Markup:
    start, end = span
    return binder.raw(
        f"BETWEEN {binder.bind('span', start)} AND {binder.bind('span', end)}"
    )


j2sql.register_filter("in_span", in_span, bind=True)

query, params = j2sql.from_string(
    """SELECT * FROM orders WHERE placed_at {{ span | in_span }}""",
    context={
        "span": (date(2026, 1, 1), date(2026, 2, 1)),
    },
)

# SELECT * FROM orders WHERE placed_at BETWEEN :span__1 AND :span__2
# {"span__1": date(2026, 1, 1), "span__2": date(2026, 2, 1)}
```

The binder gives a filter three things, and nothing else:

| method | what it does |
| --- | --- |
| `bind(name, value)` | binds one value, and returns the placeholder standing for it |
| `quote(name)` | quotes a table or column name, as the `identifier` filter does |
| `raw(sql)` | marks the result as SQL rather than as one more value to bind |

The name passed to `bind` is a prefix rather than the parameter's name, so two values bound as `span` become `:span__1` and `:span__2` and neither overwrites the other.

`raw` is what separates the two kinds of filter. Without it the fragment is bound as a single value, and the query compares a column to the string `BETWEEN :span__1 AND :span__2`.

A binder belongs to one render. Reading `j2sql.binder` outside a render raises `LookupError`, since there is nothing to bind to.

!!! warning "Changed in 0.12"

    `bind=True` used to inject the `Jinja2SQL` instance, and a filter written for it called the module-level `bind(j2sql, value, name)` or `identifier(j2sql, value)`. Both now take the binder, so such a filter becomes `binder.bind(name, value)` and `binder.quote(value)`.
