import contextlib
import os
import typing as t
from contextvars import ContextVar

import jinja2
from jinja2 import (
    BytecodeCache,
    Template,
    UndefinedError,
    defaults,
    is_undefined,
    nodes,
)
from jinja2.ext import Extension
from jinja2.lexer import Token, TokenStream
from jinja2.parser import Parser
from markupsafe import Markup
from typing_extensions import Literal

Params = t.Mapping[str, t.Any]
ParamStyle = Literal["named", "qmark", "numeric", "pyformat", "asyncpg"]


DEFAULT_IDENTIFIER_QUOTE_CHAR = ""
DEFAULT_PARAM_STYLE: ParamStyle = "named"


class RenderedQuery(t.NamedTuple):
    query: str
    params: Params


class RenderContext:
    __slots__ = (
        "param_style",
        "identifier_quote_char",
        "_params",
        "_param_index",
        "_bind_params",
    )

    def __init__(self, param_style: ParamStyle, identifier_quote_char: str):
        self._params: t.Dict[str, t.Any] = {}
        self._param_index: int = 0
        self.param_style = param_style
        self.identifier_quote_char = identifier_quote_char

    @property
    def params(self) -> t.Dict[str, t.Any]:
        """Get the parameters."""
        return self._params

    def increment_param_index(self) -> None:
        """Increment the parameter index."""
        self._param_index += 1

    def bind_param(self, name: str, value: t.Any) -> t.Tuple[str, int]:
        """Bind a parameter."""
        if is_undefined(value):
            raise UndefinedError(f"Undefined parameter '{name}' used in query.")
        self._param_index += 1
        param_key = f"{name.replace('.', '__')}_{self._param_index}"
        self._params[param_key] = value
        return param_key, self._param_index


class JinjaQ:
    def __init__(
        self,
        searchpath: t.Union[
            str, os.PathLike[str], t.Sequence[str], os.PathLike[str], None
        ] = None,
        block_start_string: str = defaults.BLOCK_START_STRING,
        block_end_string: str = defaults.BLOCK_END_STRING,
        variable_start_string: str = defaults.VARIABLE_START_STRING,
        variable_end_string: str = defaults.VARIABLE_END_STRING,
        comment_start_string: str = defaults.COMMENT_START_STRING,
        comment_end_string: str = defaults.COMMENT_END_STRING,
        line_statement_prefix: t.Union[str, None] = defaults.LINE_STATEMENT_PREFIX,
        line_comment_prefix: t.Union[str, None] = defaults.LINE_COMMENT_PREFIX,
        trim_blocks: bool = defaults.TRIM_BLOCKS,
        lstrip_blocks: bool = defaults.LSTRIP_BLOCKS,
        newline_sequence: Literal["\n", "\r\n", "\r"] = defaults.NEWLINE_SEQUENCE,
        keep_trailing_newline: bool = defaults.KEEP_TRAILING_NEWLINE,
        optimized: bool = True,
        finalize: t.Callable[..., t.Any] | None = None,
        autoescape: t.Union[bool, t.Callable[[t.Union[str, None]], bool]] = False,
        cache_size: int = 400,
        auto_reload: bool = True,
        bytecode_cache: t.Union[BytecodeCache, None] = None,
        enable_async: bool = False,
        param_style: ParamStyle = DEFAULT_PARAM_STYLE,
        identifier_quote_char: str = DEFAULT_IDENTIFIER_QUOTE_CHAR,
    ):
        # Set the Jinja loader
        loader: t.Union[jinja2.FileSystemLoader, None] = None
        if searchpath:
            loader = jinja2.FileSystemLoader(searchpath=searchpath)

        self.param_style = param_style
        self.identifier_quote_char = identifier_quote_char

        # Set the Jinja environment
        self._env = jinja2.Environment(
            block_start_string=block_start_string,
            block_end_string=block_end_string,
            variable_start_string=variable_start_string,
            variable_end_string=variable_end_string,
            comment_start_string=comment_start_string,
            comment_end_string=comment_end_string,
            line_statement_prefix=line_statement_prefix,
            line_comment_prefix=line_comment_prefix,
            trim_blocks=trim_blocks,
            lstrip_blocks=lstrip_blocks,
            newline_sequence=newline_sequence,
            keep_trailing_newline=keep_trailing_newline,
            extensions=(_JinjaQExtension,),
            optimized=optimized,
            finalize=finalize,
            autoescape=autoescape,
            cache_size=cache_size,
            auto_reload=auto_reload,
            bytecode_cache=bytecode_cache,
            enable_async=enable_async,
            loader=loader,
        )

        # Default filters
        self._env.filters["bind"] = self._bind_filter
        self._env.filters["inclause"] = self._in_clause_filter
        self._env.filters["sqlsafe"] = self._sqlsafe_filter
        self._env.filters["identifier"] = self._identifier_filter

        # Set the context variable
        self._render_context_var: ContextVar[t.Union[RenderContext, None]] = ContextVar(
            "render_context", default=None
        )

    @property
    def env(self) -> jinja2.Environment:
        """Get the Jinja environment."""
        return self._env

    def from_file(
        self,
        name: t.Union[str, Template],
        *,
        params: t.Union[Params, None] = None,
        param_style: t.Union[ParamStyle, None] = None,
        identifier_quote_char: t.Union[str, None] = None,
    ) -> RenderedQuery:
        """Load a template from a file."""
        with self._begin_render_context(
            param_style=param_style,
            identifier_quote_char=identifier_quote_char,
        ):
            template = self.env.get_template(name)
            return self._render(template, params)

    def from_string(
        self,
        source: t.Union[str, nodes.Template],
        *,
        params: t.Union[Params, None] = None,
        param_style: t.Union[ParamStyle, None] = None,
        identifier_quote_char: t.Union[str, None] = None,
    ) -> RenderedQuery:
        """Load a template from a string."""
        with self._begin_render_context(
            param_style=param_style,
            identifier_quote_char=identifier_quote_char,
        ):
            template = self.env.from_string(source)
            return self._render(template, params)

    async def from_file_async(
        self,
        name: t.Union[str, Template],
        *,
        params: t.Union[Params, None] = None,
        param_style: t.Union[ParamStyle, None] = None,
        identifier_quote_char: t.Union[str, None] = None,
    ) -> RenderedQuery:
        """Load a template from a file asynchronously."""
        with self._begin_render_context(
            param_style=param_style,
            identifier_quote_char=identifier_quote_char,
        ):
            template = self.env.get_template(name)
            return await self._render_async(template, params)

    async def from_string_async(
        self,
        source: t.Union[str, nodes.Template],
        *,
        params: t.Union[Params, None] = None,
        param_style: t.Union[ParamStyle, None] = None,
        identifier_quote_char: t.Union[str, None] = None,
    ) -> RenderedQuery:
        """Load a template from a string asynchronously."""
        with self._begin_render_context(
            param_style=param_style,
            identifier_quote_char=identifier_quote_char,
        ):
            template = self.env.from_string(source)
            return await self._render_async(template, params)

    @property
    def _render_context(self) -> RenderContext:
        """Get the template context."""
        if (render_context := self._render_context_var.get()) is None:
            raise RuntimeError("Outside of a render context.")
        return render_context

    @contextlib.contextmanager
    def _begin_render_context(
        self,
        param_style: t.Union[ParamStyle, None] = None,
        identifier_quote_char: t.Union[str, None] = None,
    ) -> t.Iterator[None]:
        """Begin a render context."""
        token = self._render_context_var.set(
            RenderContext(
                param_style=param_style or self.param_style,
                identifier_quote_char=identifier_quote_char
                or self.identifier_quote_char,
            )
        )
        try:
            yield
        finally:
            self._render_context_var.reset(token)

    def _render(self, template: Template, params: Params | None) -> RenderedQuery:
        """Render a template."""
        query = template.render(params or {})
        return RenderedQuery(
            query=query,
            params=self._render_context.params,
        )

    async def _render_async(
        self, template: Template, params: Params | None
    ) -> RenderedQuery:
        """Render a template asynchronously."""
        query = await template.render_async(params or {})
        return RenderedQuery(
            query=query,
            params=self._render_context.params,
        )

    def _bind_param(self, key: str, value: t.Any) -> str:
        """Bind a parameter."""
        param_key, param_index = self._render_context.bind_param(key, value)
        if (param_style := self._render_context.param_style) == "named":
            return f":{param_key}"
        elif param_style == "qmark":
            return "?"
        elif param_style == "numeric":
            return ":%s" % param_index
        elif param_style == "pyformat":
            return "%%(%s)s" % param_key
        elif param_style == "asyncpg":
            return f"${param_index}"
        raise ValueError(f"Invalid param_style - {param_style}")

    # Default filters

    def _bind_filter(self, value: t.Any, name: str) -> t.Union[Markup, str]:
        """Bind a parameter."""
        if isinstance(value, Markup):
            return value
        else:
            return self._bind_param(name, value)

    def _in_clause_filter(self, value: t.Any) -> str:
        """Bind an IN clause."""
        values = list(value)
        results = []
        for item in values:
            results.append(self._bind_param("inclause", item))
        clause = ",".join(results)
        clause = "(" + clause + ")"
        return clause

    @staticmethod
    def _sqlsafe_filter(value: t.Any) -> Markup:
        return Markup(value)

    def _identifier_filter(self, value: t.Any) -> Markup:
        """Format an identifier."""
        if isinstance(value, str):
            identifier = (value,)
        else:
            identifier = value
        if not isinstance(value, t.Iterable):
            raise ValueError("identifier filter expects a string or an Iterable")

        return Markup(
            ".".join(
                "".join(
                    [
                        self._render_context.identifier_quote_char,
                        item.replace(
                            self._render_context.identifier_quote_char,
                            self._render_context.identifier_quote_char * 2,
                        ),
                        self._render_context.identifier_quote_char,
                    ]
                )
                for item in identifier
            )
        )


class _JinjaQExtension(Extension):
    """JinjaQ extension."""

    def parse(self, parser: Parser) -> t.Union[nodes.Node, t.List[nodes.Node]]:
        """Parse the template."""
        return []

    def filter_stream(self, stream: TokenStream) -> t.Iterable[Token]:
        """Filter the stream."""
        while not stream.eos:
            token = next(stream)
            if token.test("variable_begin"):
                var_expr = []
                while not token.test("variable_end"):
                    var_expr.append(token)
                    token = next(stream)
                variable_end = token
                last_token = var_expr[-1]
                lineno = last_token.lineno
                if not last_token.test("name") or last_token.value not in (
                    "bind",
                    "inclause",
                    "sqlsafe",
                ):
                    param_name = self._extract_param_name(var_expr)

                    var_expr.insert(1, Token(lineno, "lparen", "("))
                    var_expr.append(Token(lineno, "rparen", ")"))
                    var_expr.append(Token(lineno, "pipe", "|"))
                    var_expr.append(Token(lineno, "name", "bind"))
                    var_expr.append(Token(lineno, "lparen", "("))
                    var_expr.append(Token(lineno, "string", param_name))
                    var_expr.append(Token(lineno, "rparen", ")"))

                var_expr.append(variable_end)
                for token in var_expr:
                    yield token
            else:
                yield token

    @staticmethod
    def _extract_param_name(tokens: t.List[Token]) -> str:
        """Extract the parameter name."""
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
        if not name:
            name = "bind_0"
        return name
