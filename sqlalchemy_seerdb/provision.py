# SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT

"""Provisioning hooks for SQLAlchemy's dialect compliance suite.

The suite asks the dialect how to do a handful of things it cannot express in
portable SQL — create a temporary table, reset a connection's default schema,
and so on. Each hook is looked up by the URL's *backend* name, which is
``oracle`` here, and a hook with no registration raises `NotImplementedError`
before the test reaches the database. That is what made the whole
`ComponentReflectionTest` class error out in setup.

Only the hooks the suite actually asks for are registered. The ones SQLAlchemy
bundles for this backend are written around a different driver's connection
API and its own CI's throwaway-database model, neither of which applies: this
suite runs against an existing account, so there is nothing to create or reap.
"""

from __future__ import annotations

from sqlalchemy.testing.provision import (
    set_default_schema_on_connection,
    temp_table_keyword_args,
)


@temp_table_keyword_args.for_db('oracle')
def _temp_table_keyword_args(cfg, eng):
    """How this backend spells a temporary table.

    Its temporary tables are *global*: the definition is permanent and shared,
    only the rows are session-private. The suite wants rows to outlive the
    transaction that inserted them, so the table has to preserve them on commit
    rather than the default of deleting them.
    """
    return {
        'prefixes': ['GLOBAL TEMPORARY'],
        'oracle_on_commit': 'PRESERVE ROWS',
    }


@set_default_schema_on_connection.for_db('oracle')
def _set_default_schema_on_connection(cfg, dbapi_connection, schema_name):
    """Point a connection's unqualified name resolution at ``schema_name``."""
    cursor = dbapi_connection.cursor()
    cursor.execute(f'ALTER SESSION SET CURRENT_SCHEMA={schema_name}')
    cursor.close()
