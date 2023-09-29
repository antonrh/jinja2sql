# Jinja2SQL (Jinja To SQL)

`Jinja2SQL` is a simple and efficient library for generating SQL queries from [Jinja2](https://jinja.palletsprojects.com/en/3.1.x/) templates. It is type-friendly and offers `async` support, drawing significant inspiration from the excellent library at [jinjasql](https://github.com/sripathikrishnan/jinjasql).

[![CI](https://github.com/antonrh/jinja2sql/actions/workflows/ci.yml/badge.svg)](https://github.com/antonrh/jinja2sql/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/antonrh/jinja2sql/branch/main/graph/badge.svg?token=67CLD19I0C)](https://codecov.io/gh/antonrh/jinja2sql)
[![Documentation Status](https://readthedocs.org/projects/jinja2sql/badge/?version=latest)](https://jinja2sql.readthedocs.io/en/latest/?badge=latest)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

---
Documentation

http://jinja2sql.readthedocs.io/

---

## Requirements

`Python 3.8+` and `Jinja2 3.1.2+`.

## Installation

Install using `pip`:

```shell
pip install jinja2sql
```

or using `poetry`:

```shell
poetry add jinja2sql
```

## Quick Example

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

### Param styles

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

| param_style | Example   |
| ----------- | --------- |
| named       | :param    |
| qmark       | ?         |
| numeric     | :1        |
| format      | %s        |
| pyformat    | %(param)s |
| asyncpg     | $1        |


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
