<!--
SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
SPDX-License-Identifier: MIT
-->

# sqlalchemy-seerdb

A SQLAlchemy dialect for the [seerdb](https://github.com/seerdb/seerdb) driver.

```python
import sqlalchemy as sa

engine = sa.create_engine('oracle+seerdb://user:password@host:1521/?service_name=XE')
```

## Why this exists

The SQL is nothing new — this inherits SQLAlchemy's built-in compiler, DDL and
reflection wholesale and supplies only what is specific to this DBAPI. What it
adds is **reach**.

seerdb speaks the wire protocol itself, in pure Python, with no vendor client
libraries. The alternatives connect directly only to newer servers and fall back
to loading vendor client libraries for anything older. So this dialect covers a
range that otherwise needs a native client installed:

| Server | This dialect | Direct connection elsewhere |
|--------|--------------|-----------------------------|
| 8i, 9i, 10g, 11g | yes | no, needs vendor client libraries |
| 12.1 and later   | yes | yes |

Verified against live servers: an 11g instance reports
`server_version_info == (11, 2, 0, 2, 0)` and a current one reports
`(23, 1, 162, 0, 0)`, both over the same dialect.

If you are on a modern server and can install a native client, the dialects that
ship with SQLAlchemy are the better-trodden path. This one is for the cases they
do not reach.

## Status

Early. Connections, Core `select`, DDL, parameter binding and reflection all
work against live servers — `has_table`, `get_columns`, `get_pk_constraint` and
`autoload_with` round-trip.

The current target is SQLAlchemy's dialect compliance suite. Progress is tracked
under the [SQLAlchemy conformance](https://github.com/seerdb/sqlalchemy-seerdb/milestone/1)
milestone.

## Running the tests

The suite is SQLAlchemy's dialect compliance suite, which upstream names as the
target for third-party dialects. It is entirely live-database driven — there is
no offline mode — so point it at a server:

```bash
pytest --dburi "oracle+seerdb://user:password@host:1521/?service_name=XE"
```

Run it from the repository root. `test.cfg` has to be found in the working
directory: SQLAlchemy's plugin reads it with configparser and does not look at
`pyproject.toml`.

### One setup step, and it needs a DBA

The suite expects a second namespace called `test_schema`, which on this backend
is a **username**, and the test account must be able to create and drop tables
inside it. Skipping this does not fail a handful of tests — every test in
`ComponentReflectionTest` errors in setup, because they share a fixture that
builds tables there.

The test account cannot create it (`ORA-01031`), so run this as a DBA once:

```
python test/prepare_test_schema.py --host localhost --service XE \
    --dba-password <SYSTEM password> --test-user <your test user>
```

It is safe to rerun: each statement is attempted on its own and one that has
already been applied is reported and skipped. What it runs, for a DBA who would
rather type it:

```sql
-- the test account's own tables must live in USERS: the Oracle dialect hides
-- SYSTEM-tablespace tables from reflection, and the suite then never empties
-- them between tests (rows "survive", ORA-00001)
ALTER USER <your test user> DEFAULT TABLESPACE USERS;
ALTER USER <your test user> QUOTA UNLIMITED ON USERS;

CREATE USER test_schema IDENTIFIED BY test_schema;
GRANT CREATE SESSION TO test_schema;
ALTER USER test_schema DEFAULT TABLESPACE USERS;
GRANT UNLIMITED TABLESPACE TO test_schema;

-- so the test account can build and drop the fixtures inside that schema;
-- SELECT ANY SEQUENCE keeps sequences in test_schema visible to reflection
GRANT CREATE ANY TABLE, DROP ANY TABLE, SELECT ANY TABLE, INSERT ANY TABLE,
      UPDATE ANY TABLE, DELETE ANY TABLE, CREATE ANY INDEX, DROP ANY INDEX,
      CREATE ANY VIEW, DROP ANY VIEW, CREATE ANY SEQUENCE, DROP ANY SEQUENCE,
      SELECT ANY SEQUENCE, COMMENT ANY TABLE, ANALYZE ANY TO <your test user>;
```

Those `ANY` privileges are broad. They are fine on a throwaway test instance —
CI creates the namespace in a container it discards — but narrow them before
granting on anything long-lived.

## Connect string

Everything after `?` is passed through to `seerdb.connect`, with integers and
booleans coerced:

```
oracle+seerdb://user:password@host:1521/?service_name=XE
oracle+seerdb://user:password@host:1521/?sid=XE&timeout=5000
```

## Licence

MIT. This repository is [REUSE](https://reuse.software/) compliant.
