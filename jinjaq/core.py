import contextlib
import os
import typing as t
from collections import defaultdict
from contextvars import ContextVar

import jinja2
import jinja2.nodes
import typing_extensions as te
from jinja2.ext import Extension
from jinja2.lexer import Token, TokenStream
from jinja2.parser import Parser
from markupsafe import Markup

_T_co = t.TypeVar("_T_co", covariant=True)


class SupportsLenAndGetItem(t.Protocol[_T_co]):
    def __len__(self) -> int:
        ...

    def __getitem__(self, __k: int) -> t.Any:
        ...


Params = t.Union[t.Mapping[str, t.Any], SupportsLenAndGetItem[t.Any]]
ParamStyle = te.Literal["named", "qmark", "format", "numeric", "pyformat", "asyncpg"]


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
        "_param_indexes",
    )

    def __init__(self, param_style: ParamStyle, identifier_quote_char: str):
        self._params: t.Dict[str, t.Any] = {}
        self._param_index: int = 0
        self._param_indexes: t.Dict[str, int] = defaultdict(lambda: 0)
        self.param_style = param_style
        self.identifier_quote_char = identifier_quote_char

    @property
    def params(self) -> Params:
        """Get the parameters."""
        if self.param_style in ("qmark", "format", "numeric", "asyncpg"):
            return tuple(self._params.values())
        return self._params

    def increment_param_index(self) -> None:
        """Increment the parameter index."""
        self._param_index += 1

    def bind_param(
        self, name: str, value: t.Any, is_in_clause: bool = False
    ) -> t.Tuple[str, int]:
        """Bind a parameter."""
        if jinja2.is_undefined(value):
            raise jinja2.UndefinedError(f"Undefined parameter '{name}' used in query.")
        self._param_index += 1
        self._param_indexes[name] += 1
        if is_in_clause:
            param_key_suffix = f"_{self._param_indexes[name]}"
        else:
            param_key_suffix = ""
        param_key = f"{name.replace('.', '__')}{param_key_suffix}"
        self._params[param_key] = value
        return param_key, self._param_index


class JinjaQ:
    def __init__(
        self,
        searchpath: t.Union[str, "os.PathLike[str]", t.Sequence[str], None] = None,
        block_start_string: str = jinja2.defaults.BLOCK_START_STRING,
        block_end_string: str = jinja2.defaults.BLOCK_END_STRING,
        variable_start_string: str = jinja2.defaults.VARIABLE_START_STRING,
        variable_end_string: str = jinja2.defaults.VARIABLE_END_STRING,
        comment_start_string: str = jinja2.defaults.COMMENT_START_STRING,
        comment_end_string: str = jinja2.defaults.COMMENT_END_STRING,
        line_statement_prefix: t.Union[
            str, None
        ] = jinja2.defaults.LINE_STATEMENT_PREFIX,
        line_comment_prefix: t.Union[str, None] = jinja2.defaults.LINE_COMMENT_PREFIX,
        trim_blocks: bool = jinja2.defaults.TRIM_BLOCKS,
        lstrip_blocks: bool = jinja2.defaults.LSTRIP_BLOCKS,
        newline_sequence: te.Literal[
            "\n", "\r\n", "\r"
        ] = jinja2.defaults.NEWLINE_SEQUENCE,
        keep_trailing_newline: bool = jinja2.defaults.KEEP_TRAILING_NEWLINE,
        optimized: bool = True,
        finalize: t.Union[t.Callable[..., t.Any], None] = None,
        cache_size: int = 400,
        auto_reload: bool = True,
        bytecode_cache: t.Union[jinja2.BytecodeCache, None] = None,
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
            extensions=(JinjaQExtension,),
            optimized=optimized,
            finalize=finalize,
            autoescape=True,
            cache_size=cache_size,
            auto_reload=auto_reload,
            bytecode_cache=bytecode_cache,
            enable_async=enable_async,
            loader=loader,
        )

        # Default filters
        self._env.filters["bind"] = self._bind_filter
        self._env.filters["_bind_in"] = self._bind_in_clause_filter
        self._env.filters["inclause"] = self._in_clause_noop_filter
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
        name: t.Union[str, jinja2.Template],
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
        source: t.Union[str, jinja2.nodes.Template],
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
        name: t.Union[str, jinja2.Template],
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
        source: t.Union[str, jinja2.nodes.Template],
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

    def _render(
        self, template: jinja2.Template, params: t.Union[Params, None]
    ) -> RenderedQuery:
        """Render a template."""
        query = template.render(params or {})
        return RenderedQuery(
            query=query,
            params=self._render_context.params,
        )

    async def _render_async(
        self, template: jinja2.Template, params: t.Union[Params, None]
    ) -> RenderedQuery:
        """Render a template asynchronously."""
        query = await template.render_async(params or {})
        return RenderedQuery(
            query=query,
            params=self._render_context.params,
        )

    def _bind_param(self, key: str, value: t.Any, is_in_clause: bool = False) -> str:
        """Bind a parameter."""
        param_key, param_index = self._render_context.bind_param(
            key, value, is_in_clause=is_in_clause
        )
        if (param_style := self._render_context.param_style) == "named":
            return f":{param_key}"
        elif param_style == "qmark":
            return "?"
        elif param_style == "format":
            return "%s"
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
        return self._bind_param(name, value)

    def _bind_in_clause_filter(self, value: t.Any, name: str) -> str:
        """Bind an IN clause."""
        values = list(value)
        results = []
        for item in values:
            results.append(self._bind_param(name, item, is_in_clause=True))
        return f"({', '.join(results)})"

    def _in_clause_noop_filter(self, value: t.Any) -> t.Any:
        return value

    def _identifier_filter(self, value: t.Any) -> Markup:
        """Format an identifier."""
        if isinstance(value, str):
            identifier = (value,)
        else:
            identifier = value
        if not isinstance(value, t.Iterable):
            raise ValueError("identifier filter expects a string or an Iterable")

        def _quote_and_escape(item: str) -> str:
            return "".join(
                [
                    self._render_context.identifier_quote_char,
                    item.replace(
                        self._render_context.identifier_quote_char,
                        self._render_context.identifier_quote_char * 2,
                    ),
                    self._render_context.identifier_quote_char,
                ]
            )

        return Markup(".".join(_quote_and_escape(item) for item in identifier))


class JinjaQExtension(Extension):
    """JinjaQ extension."""

    skip_filters = ("bind", "_bind_in", "safe")

    def parse(
        self, parser: Parser
    ) -> t.Union[jinja2.nodes.Node, t.List[jinja2.nodes.Node]]:
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
                if (
                    not last_token.test("name")
                    or last_token.value not in self.skip_filters
                ):
                    if last_token.value == "inclause":
                        filter_name = "_bind_in"
                    else:
                        filter_name = "bind"

                    param_name = self._extract_param_name(var_expr)

                    var_expr.insert(1, Token(lineno, "lparen", "("))
                    var_expr.append(Token(lineno, "rparen", ")"))
                    var_expr.append(Token(lineno, "pipe", "|"))
                    var_expr.append(Token(lineno, "name", filter_name))
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
