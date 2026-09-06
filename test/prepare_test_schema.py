# SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT
"""Prepare a database for SQLAlchemy's dialect compliance suite. Run as a DBA.

The suite needs a second namespace called ``test_schema``, which on this
backend is a user, and a test account that can build and drop fixtures inside
it. Three more things look like driver bugs until they are not, so this script
does them too: the test account's tables must live in the USERS tablespace (the
Oracle dialect hides SYSTEM-tablespace tables from reflection, and the suite
then never empties them between tests), the account needs SELECT ANY SEQUENCE
(or sequences in test_schema are invisible to reflection and get re-created),
and test_schema itself needs a quota where its objects land.

The ANY-object grants are broad. They are fine on a throwaway instance, which
is what CI uses; narrow them before running this against anything long-lived.

Every statement is attempted on its own, so a rerun against a prepared
database reports what was already there and changes nothing::

    python test/prepare_test_schema.py --host localhost --service XE \\
        --dba-password oracle --test-user pyo
"""

from __future__ import annotations

import argparse
import sys

import seerdb


def statements(test_user: str, test_schema_password: str) -> list[str]:
    user = test_user.upper()
    return [
        f'ALTER USER {user} DEFAULT TABLESPACE USERS',
        f'ALTER USER {user} QUOTA UNLIMITED ON USERS',
        f'CREATE USER test_schema IDENTIFIED BY {test_schema_password}',
        'GRANT CREATE SESSION TO test_schema',
        'ALTER USER test_schema DEFAULT TABLESPACE USERS',
        'GRANT UNLIMITED TABLESPACE TO test_schema',
        (
            'GRANT CREATE ANY TABLE, DROP ANY TABLE, SELECT ANY TABLE, '
            'INSERT ANY TABLE, UPDATE ANY TABLE, DELETE ANY TABLE, '
            'CREATE ANY INDEX, DROP ANY INDEX, CREATE ANY VIEW, DROP ANY VIEW, '
            'CREATE ANY SEQUENCE, DROP ANY SEQUENCE, SELECT ANY SEQUENCE, '
            f'COMMENT ANY TABLE, ANALYZE ANY TO {user}'
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=1521)
    parser.add_argument('--service', default='XE')
    parser.add_argument('--dba-user', default='system')
    parser.add_argument('--dba-password', required=True)
    parser.add_argument('--test-user', default='pyo')
    parser.add_argument('--test-schema-password', default='test_schema')
    args = parser.parse_args(argv)

    conn = seerdb.connect(
        host=args.host,
        port=args.port,
        service_name=args.service,
        user=args.dba_user,
        password=args.dba_password,
    )
    cur = conn.cursor()
    for statement in statements(args.test_user, args.test_schema_password):
        try:
            cur.execute(statement)
            print(f'done:    {statement[:60]}')
        except seerdb.DatabaseError as exc:
            # Already present from an earlier run, or a privilege the account
            # cannot grant: say so and carry on, the rest may still apply.
            print(f'skipped: {statement[:60]} -> {str(exc).splitlines()[0]}')
    # What the database was built with; the suite's Unicode tests depend on it.
    cur.execute(
        'SELECT parameter, value FROM nls_database_parameters '
        "WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET', "
        "'NLS_LENGTH_SEMANTICS')"
    )
    print('database NLS:', cur.fetchall())
    conn.commit()
    conn.close()
    print('test_schema ready')
    return 0


if __name__ == '__main__':
    sys.exit(main())
