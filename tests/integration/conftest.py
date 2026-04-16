import pathlib

import jinja2
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
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(sql_path))
    return Jinja2SQL(env)


@pytest.fixture(scope="session")
def async_j2sql(sql_path: pathlib.Path) -> Jinja2SQL:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(sql_path), enable_async=True
    )
    return Jinja2SQL(env)
