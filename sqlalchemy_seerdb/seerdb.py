# SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT

r"""The seerdb dialect.

Connect string::

    oracle+seerdb://user:password@host:port/?service_name=ORCLPDB1
    oracle+seerdb://user:password@host:port/?sid=XE

Query-string arguments are passed to :func:`seerdb.connect` after the ones the
URL already carries. Integers and booleans are coerced, so ``?timeout=5000`` and
``?autocommit=true`` do the expected thing.

This subclasses the *generic* dialect rather than one of the bundled
DBAPI-specific ones: those carry type handlers written against a different
driver's extension API, none of which applies here. What is left to supply is
small, because the DBAPI is already conformant and its paramstyle already
matches what the generic dialect emits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import util
from sqlalchemy.dialects.oracle.base import (
    OracleCompiler,
    OracleDialect,
    OracleExecutionContext,
)
from sqlalchemy.engine import cursor as _cursor

if TYPE_CHECKING:
    from sqlalchemy.engine.url import URL

# Query-string arguments that are not strings on the driver's side.
_INT_ARGS = frozenset({'port', 'timeout', 'sdu', 'field_version', 'purity', 'fetch'})
_BOOL_ARGS = frozenset({'autocommit', 'ssl', 'prelim'})
_TRUTHY = frozenset({'1', 'true', 'yes', 'on'})


def _coerce(key: str, value: str) -> Any:
    if key in _INT_ARGS:
        return int(value)
    if key in _BOOL_ARGS:
        return value.strip().lower() in _TRUTHY
    return value


class SeerdbExecutionContext(OracleExecutionContext):
    """Turns this backend's RETURNING into the rows SQLAlchemy expects.

    There is no result set for RETURNING here. The compiler already emits the
    form the server wants — `RETURNING id INTO :ret_0` — and the values come
    back on those binds afterwards, which is a shape SQLAlchemy has no idea
    what to do with on its own: it asks the cursor for rows and finds none.

    So the values are collected off the binds after execution and handed back
    as a fully buffered result, which is what the caller was expecting all
    along. `inserted_primary_key` rides on the same path.
    """

    out_parameters: dict | None = None

    def _returning_var_type(self, index):
        """The bind type for one returned column, from what the query says."""
        columns = self.compiled._result_columns
        if index < len(columns):
            sqla_type = columns[index].type
            try:
                impl = sqla_type.dialect_impl(self.dialect)
                dbapi_type = impl.get_dbapi_type(self.dialect.loaded_dbapi)
            except (AttributeError, NotImplementedError):
                dbapi_type = None
            # A float column maps to the same numeric type as everything else,
            # and the driver hands that back as a Decimal. Binding the receiver
            # as a float instead keeps the value the type the query asked for.
            try:
                if sqla_type.python_type is float:
                    return float
            except (AttributeError, NotImplementedError):
                pass
            if dbapi_type is not None:
                return dbapi_type
        # A returned column whose type does not map cleanly still has to be
        # bound as something; a string accepts whatever comes back.
        return str

    def pre_exec(self):
        super().pre_exec()
        compiled = self.compiled
        if not getattr(compiled, '_oracle_returning', False):
            return
        # Bind a receiver per returned column, in the order the compiler named
        # them, and hand them to the driver in place of the plain values.
        self.out_parameters = {}
        names = [f'ret_{i}' for i in range(len(compiled._result_columns))]
        for index, name in enumerate(names):
            var = self.cursor.var(self._returning_var_type(index))
            self.out_parameters[name] = var
            if isinstance(self.parameters, list):
                for parameter_set in self.parameters:
                    parameter_set[name] = var
            else:
                self.parameters[name] = var

    def get_out_parameter_values(self, names):
        assert self.out_parameters is not None
        return [self.out_parameters[name].getvalue() for name in names]

    def fetchall_for_returning(self, cursor):
        """The returned values, shaped as rows."""
        if not self.out_parameters:
            return []
        columns = []
        for index, entry in enumerate(self.compiled._result_columns):
            value = self.out_parameters[f'ret_{index}'].getvalue()
            # A receiver reports its value as a list, one entry per affected
            # row, so a single-row statement still arrives wrapped.
            values = value if isinstance(value, list) else [value]
            columns.append([self._coerce_returned(entry, v) for v in values])
        return list(zip(*columns)) if columns else []

    @staticmethod
    def _coerce_returned(entry, value):
        """Give a returned value the type the query asked for.

        The driver decides a numeric value's Python type from the value rather
        than from the receiver it was given, so a float column arrives as a
        Decimal even when the receiver asked for a float (seerdb#688). Comparing
        that against what was inserted then fails on the type. Drop this once
        the driver honours the requested type.
        """
        if value is None:
            return value
        try:
            wanted = entry.type.python_type
        except (AttributeError, NotImplementedError):
            return value
        if wanted is float and not isinstance(value, float):
            return float(value)
        return value

    def post_exec(self):
        compiled = self.compiled
        if compiled is not None and getattr(compiled, '_oracle_returning', False):
            self.cursor_fetch_strategy = _cursor.FullyBufferedCursorFetchStrategy(
                self.cursor,
                [(entry.keyname, None) for entry in compiled._result_columns],
                initial_buffer=self.fetchall_for_returning(self.cursor),
            )
        super().post_exec()


class SeerdbCompiler(OracleCompiler):
    """Renders bind names this server will actually accept.

    The server is far pickier about bind names than SQL generally is. A name may
    not start with a digit or an underscore, and a good many punctuation
    characters are rejected outright with "invalid host/bind variable name" —
    which is what a name like ``/slashes/`` or ``q?marks`` produces. Names like
    those are not contrived: they come from column names, and a caller who names
    a column that way gets a bind named after it.

    Two mechanisms are needed, because neither covers the other:

    * an escape map, used for the expanded parameters of an ``IN`` clause, where
      quoting is not available; and
    * quoting the name outright everywhere else, which also handles reserved
      words and the illegal leading characters.
    """

    # The generic compiler escapes eight characters. These three more are
    # rejected by this server and have to travel as an escape rather than a
    # quoted name, because an expanded parameter cannot be quoted.
    bindname_escape_characters = util.immutabledict(
        {
            '%': 'P',
            '(': 'A',
            ')': 'Z',
            ':': 'C',
            '.': 'C',
            '[': 'C',
            ']': 'C',
            ' ': 'C',
            '\\': 'C',
            '/': 'C',
            '?': 'C',
        }
    )

    def bindparam_string(self, name, **kw):
        """Rewrite a bind name into one the server accepts.

        Escaping only, never quoting. The quoted form `:"name"` is what the
        bundled dialects lean on, but this driver does not parse it — the
        placeholder goes unrecognised and the value is reported as never
        provided. Escaping covers the same ground and works everywhere,
        including the expanded parameters of an `IN` clause, where quoting is
        not available anyway.

        The original name is recorded in `escaped_from` so the value still
        binds to it.
        """
        if not kw.get('escaped_from'):
            translated = name
            if self._bind_translate_re.search(name):
                translated = self._bind_translate_re.sub(
                    lambda m: self._bind_translate_chars[m.group(0)], name
                )
            # Escaping the characters is not the whole job. A reserved word
            # (`desc`) and an illegal leading character (a digit or an
            # underscore) are both still rejected, and both are what quoting
            # would normally have solved. A prefix does the same work: the name
            # only has to be unique and legal.
            if self.preparer._bindparam_requires_quotes(translated):
                translated = 'D' + translated
            if translated != name:
                kw['escaped_from'] = name
                name = translated
        return super().bindparam_string(name, **kw)


class SeerdbDialect(OracleDialect):
    """SQLAlchemy dialect driving the seerdb DBAPI."""

    name = 'oracle'
    driver = 'seerdb'
    statement_compiler = SeerdbCompiler
    execution_ctx_cls = SeerdbExecutionContext

    # RETURNING works through SeerdbExecutionContext above, which collects the
    # values off the OUT binds the compiler emits and presents them as rows.
    insert_returning = True
    update_returning = True
    delete_returning = True
    # Separately broken in the driver, which corrupts the wire protocol for it
    # past one row (seerdb#687).
    insert_executemany_returning = False

    # No SQL is generated differently from the base dialect, so cached
    # statements stay valid.
    supports_statement_cache = True

    @classmethod
    def import_dbapi(cls) -> Any:
        import seerdb

        return seerdb

    # Kept for SQLAlchemy 1.4 callers, which look for the old spelling.
    @classmethod
    def dbapi(cls) -> Any:
        return cls.import_dbapi()

    def create_connect_args(self, url: URL) -> tuple[list, dict]:
        options: dict[str, Any] = {}
        if url.host:
            options['host'] = url.host
        if url.port:
            options['port'] = url.port
        if url.username:
            options['user'] = url.username
        if url.password:
            options['password'] = url.password
        # A bare path is the service name, so both the modern URL form and the
        # query-string form work.
        if url.database:
            options.setdefault('service_name', url.database)
        for key, value in url.query.items():
            # A repeated key arrives as a tuple; the driver takes one value.
            options[key] = _coerce(
                key, value[-1] if isinstance(value, tuple) else value
            )
        return ([], options)

    def _get_server_version_info(self, connection: Any) -> tuple[int, ...]:
        # The driver already decodes the packed release the server sends at
        # login, so there is no round trip to make here.
        raw = getattr(connection.connection, 'version', None)
        if not raw:
            return ()
        parts = []
        for piece in str(raw).split('.'):
            try:
                parts.append(int(piece))
            except ValueError:
                break
        return tuple(parts)

    def is_disconnect(self, e: Exception, connection: Any, cursor: Any) -> bool:
        if isinstance(e, self.loaded_dbapi.InterfaceError):
            return True
        return super().is_disconnect(e, connection, cursor)


dialect = SeerdbDialect
