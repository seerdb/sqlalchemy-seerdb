# SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT
"""Drop what the compliance suite left behind, so a rerun starts clean.

The suite compares whole object lists -- ``ComponentReflectionTest`` asserts on
the set of tables a schema contains -- so anything left over from an earlier run
fails tests that have nothing to do with it. CI never meets this because it
starts a throwaway database per run; a database you keep accumulates, and the
suite's pass count drifts away from CI's for reasons that look like driver bugs.

This is the companion to ``prepare_test_schema.py``: that one creates the
accounts and grants once, this one empties them between runs.

Objects are found and dropped through the Oracle data dictionary over an
ordinary connection, not with SQL for one particular backend, so the same script
resets a real Oracle and a Mirror standing in front of PostgreSQL.

**It only reports by default.** Dropping every table in a schema is not
something to do by accident, so a plain run prints what it would remove and
changes nothing; pass ``--drop`` to actually do it::

    python test/reset_test_schema.py --host localhost --port 1521 --service XE
    python test/reset_test_schema.py --host localhost --service XE --drop

Point it only at a database that exists to be reset.
"""

from __future__ import annotations

import argparse
import sys

import seerdb

# Dropped before tables, because a view over a table about to go stops the table
# dropping cleanly; sequences are independent and go last.
# Each kind lists the statements to try in order. A table is dropped with
# CASCADE CONSTRAINTS first, because on Oracle a table referenced by a foreign
# key will not go without it; a Mirror in front of PostgreSQL rejects that
# spelling (ORA-00900), so a plain DROP follows as the fallback.
#
# Object tables (CREATE TABLE ... OF some_type) are a kind of their own because
# USER_TABLES does not list them -- only USER_OBJECT_TABLES / USER_ALL_TABLES do
# -- while the dialect's reflection (ALL_TABLES) sees them like any other table.
# One such leftover, from a driver test suite sharing the schema, failed 41
# ComponentReflectionTest cases that compare the whole table set. The types they
# are built on go after them (a type in use by a table will not drop) and
# before the sequences; FORCE first, because a type referenced by another type
# needs it, then the plain spelling for a backend without it.
_KINDS = (
    ('view', 'sys.user_views', ('DROP VIEW {name}',)),
    (
        'table',
        'sys.user_tables',
        ('DROP TABLE {name} CASCADE CONSTRAINTS', 'DROP TABLE {name}'),
    ),
    (
        'object table',
        'sys.user_object_tables',
        ('DROP TABLE {name} CASCADE CONSTRAINTS', 'DROP TABLE {name}'),
    ),
    ('type', 'sys.user_types', ('DROP TYPE {name} FORCE', 'DROP TYPE {name}')),
    ('sequence', 'sys.user_sequences', ('DROP SEQUENCE {name}',)),
)

# Schema-qualified on purpose. Against a Mirror standing in front of PostgreSQL
# an unqualified `user_tables` resolves to something else entirely -- it answered
# with 73 rows of PostgreSQL catalogs where `sys.user_tables` answered with the
# 4 real ones -- and a reset that believed the first list would try to drop the
# server's own catalogs. Qualifying costs nothing on a real Oracle.
_NAME_COLUMN = {
    'sys.user_views': 'view_name',
    'sys.user_tables': 'table_name',
    'sys.user_object_tables': 'table_name',
    'sys.user_types': 'type_name',
    'sys.user_sequences': 'sequence_name',
}


def _objects(cur, view: str) -> list[str]:
    """Every object of one kind owned by the connected account, or [] if the
    backend does not offer that dictionary view at all."""
    column = _NAME_COLUMN[view]
    try:
        cur.execute(f'SELECT {column} FROM {view}')
    except seerdb.DatabaseError as exc:
        # A backend that does not implement this view has nothing of that kind
        # to clean; say so rather than failing the whole reset.
        print(f'  ({view} unavailable: {str(exc).splitlines()[0]})')
        return []
    return [row[0] for row in cur.fetchall() if row and row[0]]


def reset(conn, *, drop: bool) -> tuple[int, int]:
    """Report -- and with ``drop``, remove -- the account's objects.

    Returns ``(found, removed)``. They differ when something could not be
    dropped, and the caller says so: a reset that reports success it did not
    achieve is worse than one that fails loudly, because the next suite run
    inherits the mess and blames itself.
    """
    cur = conn.cursor()
    found = removed = 0
    for kind, view, statements in _KINDS:
        names = _objects(cur, view)
        found += len(names)
        for name in names:
            if not drop:
                print(f'would drop {kind}: {name}')
                continue
            # Try the bare name before the quoted one. The dictionary reports
            # names in Oracle's folded (upper) form, which a bare DROP folds the
            # same way on either backend; quoting that form instead asks for a
            # literally upper-case object, which on a Mirror over PostgreSQL --
            # where the table is really lower-case -- does not exist. The quoted
            # spelling still follows, because the suite deliberately creates
            # mixed-case and reserved-word objects that need it.
            last = None
            for spelling in (name, f'"{name}"'):
                for statement in statements:
                    try:
                        cur.execute(statement.format(name=spelling))
                        print(f'dropped {kind}: {name}')
                        removed += 1
                        last = None
                        break
                    except seerdb.DatabaseError as exc:
                        last = exc
                if last is None:
                    break
            if last is not None:
                # Already gone with a CASCADE above, or genuinely undroppable.
                # Either way the rest are still worth clearing.
                print(f'skipped {kind}: {name} -> {str(last).splitlines()[0]}')
    if drop:
        conn.commit()
    return (found, removed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=1521)
    parser.add_argument('--service', default='XE')
    parser.add_argument('--user', default='pyo')
    parser.add_argument('--password', default='pyo123')
    parser.add_argument(
        '--drop',
        action='store_true',
        help='actually drop the objects (without this, only report them)',
    )
    args = parser.parse_args(argv)

    conn = seerdb.connect(
        host=args.host,
        port=args.port,
        service_name=args.service,
        user=args.user,
        password=args.password,
    )
    try:
        (found, removed) = reset(conn, drop=args.drop)
    finally:
        conn.close()

    if not found:
        print(f'{args.user}: nothing to clean')
        return 0
    if not args.drop:
        print(f'{args.user}: {found} object(s) would be dropped; pass --drop')
        return 0
    print(f'{args.user}: {removed} of {found} object(s) dropped')
    # Leftovers are the whole reason this script exists, so failing to remove
    # them is a failure, not a note in passing.
    return 0 if removed == found else 1


if __name__ == '__main__':
    sys.exit(main())
