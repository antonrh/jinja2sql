from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextvars import ContextVar
from typing import (
    Any,
    Concatenate,
    Literal,
    ParamSpec,
    Protocol,
    TypeAlias,
    TypeVar,
    overload,
)

import jinja2
import jinja2.nodes
from jinja2.ext import Extension
from jinja2.lexer import Token, TokenStream
from jinja2.parser import Parser
from markupsafe import Markup

T = TypeVar("T")
P = ParamSpec("P")

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------


class ParamStyleFunc(Protocol):
    def __call__(self, param_key: str, param_index: int) -> str: ...


ParamStyle = Literal["named", "qmark", "format", "numeric", "pyformat", "asyncpg"]
Params: TypeAlias = Mapping[str, Any] | Sequence[Any]
Context: TypeAlias = Mapping[str, Any]

DEFAULT_PARAM_STYLE: ParamStyle = "named"
DEFAULT_IDENTIFIER_QUOTE_CHAR = ""

# ---------------------------------------------------------------------------
# Binder — per-render state
# ---------------------------------------------------------------------------


class Binder:
    """The values one render binds, and how it writes them.

    A filter registered with ``bind=True`` is called with the binder of the
    render in front of its own arguments:

    ```python
    def in_span(binder: Binder, span: tuple[date, date]) -> Markup:
        start, end = span
        return binder.raw(
            f"BETWEEN {binder.bind('span', start)} AND {binder.bind('span', end)}"
        )
    ```
    """

    __slots__ = (
        "param_style",
        "identifier_quote_char",
        "_params",
        "_param_index",
    )

    def __init__(
        self,
        param_style: ParamStyle | ParamStyleFunc,
        identifier_quote_char: str,
    ) -> None:
        self._params: list[Any] | dict[str, Any] = {}
        if _is_positional_param_style(param_style):
            self._params = []
        self._param_index: int = 0
        self.param_style = param_style
        self.identifier_quote_char = identifier_quote_char

    @property
    def params(self) -> Params:
        """Get the parameters bound so far."""
        return self._params

    def bind(self, name: str, value: Any, *, in_clause: bool = False) -> str:
        """Bind a value and return the placeholder standing for it.

        The name is a prefix rather than the parameter's name, so two values
        bound as `span` are `:span__1` and `:span__2`.
        """
        param_key, param_index = self.bind_param(name, value, in_clause=in_clause)
        if callable(param_style := self.param_style):
            return param_style(param_key, param_index)
        elif param_style == "named":
            return f":{param_key}"
        elif param_style == "qmark":
            return "?"
        elif param_style == "format":
            return "%s"
        elif param_style == "numeric":
            return f":{param_index}"
        elif param_style == "pyformat":
            return f"%({param_key})s"
        elif param_style == "asyncpg":
            return f"${param_index}"
        raise ValueError(f"Invalid param_style - {param_style}")

    def quote(self, value: Any) -> Markup:
        """Quote a table or column name the way this render quotes one."""
        if isinstance(value, str):
            parts: Iterable[str] = (value,)
        elif isinstance(value, Iterable):
            parts = value
        else:
            raise ValueError("identifier filter expects a string or an Iterable")

        quote = self.identifier_quote_char
        return Markup(
            ".".join(
                f"{quote}{item.replace(quote, quote * 2)}{quote}" for item in parts
            )
        )

    def raw(self, sql: str) -> Markup:
        """Mark a fragment as SQL, rather than as one more value to bind."""
        return Markup(sql)

    def bind_param(
        self, name: str, value: Any, *, in_clause: bool = False
    ) -> tuple[str, int]:
        """Bind a value, and return the key it took and its position."""
        if jinja2.is_undefined(value):
            raise jinja2.UndefinedError(f"Undefined parameter '{name}' used in query.")
        self._param_index += 1
        if in_clause:
            param_key_suffix = f"__in__{self._param_index}"
        else:
            param_key_suffix = f"__{self._param_index}"
        param_key = f"{name.replace('.', '__')}{param_key_suffix}"
        if isinstance(self._params, dict):
            self._params[param_key] = value
        else:
            self._params.append(value)
        return param_key, self._param_index


# ---------------------------------------------------------------------------
# Public filter functions
# ---------------------------------------------------------------------------


def bind(binder: Binder, value: Any, name: str) -> Markup | str:
    """Bind a parameter value to a SQL placeholder."""
    if isinstance(value, Markup):
        return value
    return binder.bind(name, value)


def bind_in(binder: Binder, value: Any, name: str) -> str:
    """Bind multiple values for an IN clause."""
    values = list(value)
    if not values:
        raise ValueError("IN clause cannot be empty.")
    results = [binder.bind(name, item, in_clause=True) for item in values]
    return f"({', '.join(results)})"


def identifier(binder: Binder, value: Any) -> Markup:
    """Escape and quote a SQL identifier."""
    return binder.quote(value)


# ---------------------------------------------------------------------------
# Jinja2SQL — main class
# ---------------------------------------------------------------------------


class Jinja2SQL:
    def __init__(
        self,
        env: jinja2.Environment | None = None,
        *,
        param_style: ParamStyle = DEFAULT_PARAM_STYLE,
        identifier_quote_char: str = DEFAULT_IDENTIFIER_QUOTE_CHAR,
        autobind: bool = True,
    ):
        self.param_style = param_style
        self.identifier_quote_char = identifier_quote_char
        self.binder_var: ContextVar[Binder] = ContextVar("binder")

        if env is None:
            env = jinja2.Environment()
        if autobind:
            env.add_extension(_AutoBindExtension)
        env.autoescape = True
        self._env = env

        # Built-in filters
        self.register_filter("bind", bind, bind=True)
        self.register_filter("inclause", bind_in, bind=True)
        self.register_filter("identifier", identifier, bind=True)

    # -- Properties ---------------------------------------------------------

    @property
    def env(self) -> jinja2.Environment:
        """Get the Jinja environment."""
        return self._env

    @property
    def binder(self) -> Binder:
        """The binder of the render running now.

        Raises:
            LookupError: outside a render, where there is nothing to bind to.
        """
        return self.binder_var.get()

    # -- Filter registration ------------------------------------------------

    @overload
    def register_filter(self, name: str, func: Callable[..., Any]) -> None: ...

    @overload
    def register_filter(
        self,
        name: str,
        func: Callable[Concatenate[Binder, P], T],
        *,
        bind: Literal[True],
    ) -> None: ...

    def register_filter(
        self, name: str, func: Callable[..., Any], *, bind: bool = False
    ) -> None:
        """Register a filter.

        With ``bind=True`` the filter is called with the `Binder` of the render
        in front of its own arguments, which is what a filter writing SQL of its
        own binds the values in it through.
        """
        if bind:
            self._env.filters[name] = lambda *args, **kwargs: func(
                self.binder, *args, **kwargs
            )
        else:
            self._env.filters[name] = func

    @overload
    def filter(self, func: Callable[P, T]) -> Callable[P, T]: ...

    @overload
    def filter(
        self, *, name: str | None = None
    ) -> Callable[[Callable[P, T]], Callable[P, T]]: ...

    @overload
    def filter(
        self, *, name: str | None = None, bind: Literal[True]
    ) -> Callable[
        [Callable[Concatenate[Binder, P], T]],
        Callable[Concatenate[Binder, P], T],
    ]: ...

    def filter(
        self,
        func: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        bind: bool = False,
    ) -> Any:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _name = name or func.__name__
            if bind:
                self.register_filter(_name, func, bind=True)
            else:
                self.register_filter(_name, func)
            return func

        if func is None:
            return decorator
        return decorator(func)

    # -- Rendering ----------------------------------------------------------

    def from_string(
        self,
        source: str | jinja2.nodes.Template,
        *,
        context: Context | None = None,
        param_style: ParamStyle | ParamStyleFunc | None = None,
        identifier_quote_char: str | None = None,
    ) -> tuple[str, Params]:
        """Generate SQL from a string template."""
        with self._begin_render(
            param_style=param_style,
            identifier_quote_char=identifier_quote_char,
        ):
            template = self.env.from_string(source)
            return self._render(template, context)

    def from_file(
        self,
        name: str | jinja2.Template,
        *,
        context: Context | None = None,
        param_style: ParamStyle | ParamStyleFunc | None = None,
        identifier_quote_char: str | None = None,
    ) -> tuple[str, Params]:
        """Generate SQL from a file template."""
        with self._begin_render(
            param_style=param_style,
            identifier_quote_char=identifier_quote_char,
        ):
            template = self.env.get_template(name)
            return self._render(template, context)

    async def from_string_async(
        self,
        source: str | jinja2.nodes.Template,
        *,
        context: Context | None = None,
        param_style: ParamStyle | ParamStyleFunc | None = None,
        identifier_quote_char: str | None = None,
    ) -> tuple[str, Params]:
        """Generate SQL from a string template asynchronously."""
        with self._begin_render(
            param_style=param_style,
            identifier_quote_char=identifier_quote_char,
        ):
            template = self.env.from_string(source)
            return await self._render_async(template, context)

    async def from_file_async(
        self,
        name: str | jinja2.Template,
        *,
        context: Context | None = None,
        param_style: ParamStyle | ParamStyleFunc | None = None,
        identifier_quote_char: str | None = None,
    ) -> tuple[str, Params]:
        """Generate SQL from a file template asynchronously."""
        with self._begin_render(
            param_style=param_style,
            identifier_quote_char=identifier_quote_char,
        ):
            template = self.env.get_template(name)
            return await self._render_async(template, context)

    # -- Internal -----------------------------------------------------------

    @contextlib.contextmanager
    def _begin_render(
        self,
        param_style: ParamStyle | ParamStyleFunc | None = None,
        identifier_quote_char: str | None = None,
    ) -> Iterator[None]:
        token = self.binder_var.set(
            Binder(
                param_style=param_style
                if param_style is not None
                else self.param_style,
                identifier_quote_char=identifier_quote_char
                if identifier_quote_char is not None
                else self.identifier_quote_char,
            )
        )
        try:
            yield
        finally:
            self.binder_var.reset(token)

    def _render(
        self, template: jinja2.Template, context: Context | None
    ) -> tuple[str, Params]:
        query = template.render(context or {})
        return query, self.binder.params

    async def _render_async(
        self, template: jinja2.Template, context: Context | None
    ) -> tuple[str, Params]:
        query = await template.render_async(context or {})
        return query, self.binder.params


# ---------------------------------------------------------------------------
# Jinja2SQL Extension — auto-binds template variables
# ---------------------------------------------------------------------------


class _AutoBindExtension(Extension):
    skip_filters = ("bind", "inclause")

    def parse(self, parser: Parser) -> jinja2.nodes.Node | list[jinja2.nodes.Node]:
        return []

    def filter_stream(self, stream: TokenStream) -> Iterable[Token]:
        while not stream.eos:
            token = next(stream)
            if token.test("variable_begin"):
                var_expr: list[Token] = []
                while not token.test("variable_end"):
                    var_expr.append(token)
                    token = next(stream)
                variable_end = token
                lineno = var_expr[-1].lineno

                filter_names = self._filter_names(var_expr)
                has_inclause = "inclause" in filter_names
                has_skip = any(n in self.skip_filters for n in filter_names)

                if has_inclause and not self._has_inclause_args(var_expr):
                    # Add param name argument to inclause
                    param_name = self._extract_param_name(var_expr)
                    self._inject_inclause_arg(var_expr, param_name, lineno)
                elif not has_skip:
                    # Wrap with bind filter
                    param_name = self._extract_param_name(var_expr)
                    var_expr.insert(1, Token(lineno, "lparen", "("))
                    var_expr.append(Token(lineno, "rparen", ")"))
                    var_expr.append(Token(lineno, "pipe", "|"))
                    var_expr.append(Token(lineno, "name", "bind"))
                    var_expr.append(Token(lineno, "lparen", "("))
                    var_expr.append(Token(lineno, "string", param_name))
                    var_expr.append(Token(lineno, "rparen", ")"))

                var_expr.append(variable_end)
                yield from var_expr
            else:
                yield token

    @staticmethod
    def _filter_names(tokens: list[Token]) -> list[str]:
        """Extract filter names from a variable expression (names after pipe)."""
        names: list[str] = []
        after_pipe = False
        for token in tokens:
            if token.test("pipe"):
                after_pipe = True
            elif after_pipe and token.test("name"):
                names.append(token.value)
                after_pipe = False
        return names

    @staticmethod
    def _has_inclause_args(tokens: list[Token]) -> bool:
        """Check if inclause already has arguments (e.g. inclause('name'))."""
        found_inclause = False
        for token in tokens:
            if found_inclause and token.test("lparen"):
                return True
            found_inclause = token.test("name") and token.value == "inclause"
        return False

    @staticmethod
    def _inject_inclause_arg(tokens: list[Token], param_name: str, lineno: int) -> None:
        """Add param name argument to an existing inclause filter."""
        for i, token in enumerate(tokens):
            if token.test("name") and token.value == "inclause":
                tokens.insert(i + 1, Token(lineno, "lparen", "("))
                tokens.insert(i + 2, Token(lineno, "string", param_name))
                tokens.insert(i + 3, Token(lineno, "rparen", ")"))
                return

    @staticmethod
    def _extract_param_name(tokens: list[Token]) -> str:
        name = ""
        for token in tokens:
            if token.test("variable_begin"):
                continue
            elif token.test("name"):
                name += token.value
            elif token.test("dot"):
                name += token.value
            else:
                break
        return name or "bind_0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_positional_param_style(
    param_style: ParamStyle | ParamStyleFunc,
) -> bool:
    if param_style in ("qmark", "format", "numeric", "asyncpg"):
        return True
    if callable(param_style):
        return "key" not in param_style("key", 0)
    return False
