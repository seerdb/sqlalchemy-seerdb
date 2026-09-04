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
from sqlalchemy.dialects.oracle.base import OracleCompiler, OracleDialect

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

    # This backend does not return a result set for RETURNING — it returns the
    # values through OUT binds — and this dialect has no bridge for that yet
    # (#6). Claiming the capability is worse than not having it: SQLAlchemy
    # would generate RETURNING for ordinary ORM inserts and then fail at
    # runtime on a result that carries no rows. Declared off so it takes the
    # working path instead. Turn back on with #6.
    insert_returning = False
    update_returning = False
    delete_returning = False
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
