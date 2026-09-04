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

Early. Connections, Core `select`, DDL and parameter binding work against live
servers. Reflection is **blocked** on a driver bug where a `NULL` literal column
desyncs the row decoder, which the reflection query trips over — see
[seerdb#682](https://github.com/seerdb/seerdb/issues/682).

The next milestone is SQLAlchemy's dialect compliance suite, which upstream names
as the target for third-party dialects.

## Connect string

Everything after `?` is passed through to `seerdb.connect`, with integers and
booleans coerced:

```
oracle+seerdb://user:password@host:1521/?service_name=XE
oracle+seerdb://user:password@host:1521/?sid=XE&timeout=5000
```

## Licence

MIT. This repository is [REUSE](https://reuse.software/) compliant.
