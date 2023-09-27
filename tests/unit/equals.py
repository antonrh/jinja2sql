from textwrap import dedent
from typing import Any, TypeVar, cast

from dirty_equals import DirtyEquals

T = TypeVar("T")


class IsSQL(DirtyEquals[T]):
    expected_types = (str,)

    def __init__(self, sql: str, *repr_args: Any, **repr_kwargs: Any) -> None:
        super().__init__(*repr_args, **repr_kwargs)
        self.sql = sql

    def equals(self, other: Any) -> bool:
        if type(other) not in self.expected_types:
            return False

        return (
            dedent(self.sql).strip().lower() == dedent(cast(str, other)).strip().lower()
        )
