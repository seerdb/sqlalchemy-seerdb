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

from sqlalchemy.dialects.oracle.base import OracleDialect

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


class SeerdbDialect(OracleDialect):
    """SQLAlchemy dialect driving the seerdb DBAPI."""

    name = 'oracle'
    driver = 'seerdb'

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
