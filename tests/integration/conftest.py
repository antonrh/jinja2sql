import pathlib

import pytest

from jinja2sql._core import Jinja2SQL


@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig: pytest.Config) -> list[pathlib.Path]:
    base_dir = pytestconfig.rootpath / "tests/integration"
    return [base_dir / "docker-compose.yml"]


@pytest.fixture(scope="session")
def sql_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "sql"


@pytest.fixture(scope="session")
def j2sql(sql_path: pathlib.Path) -> Jinja2SQL:
    return Jinja2SQL(searchpath=sql_path)


@pytest.fixture(scope="session")
def async_j2sql(sql_path: pathlib.Path) -> Jinja2SQL:
    return Jinja2SQL(searchpath=sql_path, enable_async=True)
