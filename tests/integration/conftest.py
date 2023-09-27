import pathlib

import pytest

from jinjaq.core import JinjaQ


@pytest.fixture(scope="session")
def sql_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "sql"


@pytest.fixture(scope="session")
def jq(sql_path: pathlib.Path) -> JinjaQ:
    return JinjaQ(searchpath=sql_path)


@pytest.fixture(scope="session")
def async_jq(sql_path: pathlib.Path) -> JinjaQ:
    return JinjaQ(searchpath=sql_path, enable_async=True)
