# Usage

`Jinja2SQL` provides a `jinja2sql.Jinja2SQL` class that can be used to generate SQL queries from string or file templates.

## String Templates

To generate SQL queries from string templates, use the `from_string` method:

```python

```python
from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL(param_style="named")  # default param style is "named"

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

from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL(searchpath=Path(__name__).parent)  # default param style is "named"

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

`Jinja2SQL` supports asynchroneous query generation using the `enable_async` flag:

```python
from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL(enable_async=True)
```

### String Templates

To generate SQL queries from string templates, use the `from_string_async` method:

```python
import asyncio

from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL(param_style="named", enable_async=True)


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

from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL(searchpath=Path(__name__).parent, enable_async=True)


async def main() -> None:
    query, params = await j2sql.from_file_async(
        "query.sql",
        context={"table": "users", "email": "user@mail.com"},
    )

    assert query == "SELECT * FROM users WHERE email = :email"
    assert params == {"email": "user@mail.com"}


asyncio.run(main())
```

## Customer filters

`Jinja2SQL` supports custom filters to extend the functionality of the Jinja2 templating engine.

To add custom filters, use the `register_filter` method or `@filter` decorator:

```python
from jinja2sql import Jinja2SQL

j2sql = Jinja2SQL()


@j2sql.filter(name="array")   # or j2sql.register_filter("array", array_filter)
def array_filter(self: Jinja2SQL, value: list[str]) -> str:
    return self.identifier(", ".join(f"'{item}'" for item in value))


query, params = j2sql.from_string(
    """SELECT ARRAY[{{ param | array2 }}] AS array""",
    context={
        "param": ["0", "1"],
    },
)
```
