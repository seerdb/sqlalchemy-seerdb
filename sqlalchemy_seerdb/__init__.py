# SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT

"""A SQLAlchemy dialect for the seerdb driver.

Registered through the ``sqlalchemy.dialects`` entry point, so a URL of
``oracle+seerdb://user:password@host:port/?service_name=…`` selects it.

The SQL that goes over the wire is the same dialect SQLAlchemy already speaks,
so this package inherits the built-in compiler, DDL and reflection wholesale and
supplies only what is specific to this DBAPI. What it adds is *reach*: seerdb
speaks the wire protocol itself, so the dialect works against server versions
that the alternatives can only reach by loading vendor client libraries.
"""

from __future__ import annotations

from sqlalchemy_seerdb.seerdb import SeerdbDialect

__all__ = ['SeerdbDialect', '__version__']

__version__ = '0.1.0.dev0'
