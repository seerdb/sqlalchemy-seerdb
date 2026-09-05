# SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT

"""Hook the dialect into SQLAlchemy's compliance suite.

Upstream names that suite as the target for third-party dialects, so it is what
this package tests against rather than a bespoke set of its own. Point it at a
live server with, for example::

    pytest --dburi oracle+seerdb://user:password@host:1521/?service_name=XE
"""

import pytest
from sqlalchemy.dialects import registry

registry.register('oracle.seerdb', 'sqlalchemy_seerdb.seerdb', 'SeerdbDialect')

# Importing this registers the provisioning hooks the suite looks up by backend
# name; without it the hooks are missing and whole classes error in setup.
import sqlalchemy_seerdb.provision  # noqa: F401

pytest.register_assert_rewrite('sqlalchemy.testing.assertions')

from sqlalchemy.testing.plugin.pytestplugin import *


def pytest_configure(config):
    # A diagnostic trace of what reaches the driver, one stderr line per call,
    # switched on with SEERDB_SPY=1. Meant for CI runs with output uncaptured
    # (`-s`): the 11g compliance job sees rows survive the per-test DELETE
    # while no local run does, and the log has to say which connection did
    # what, in which order, for that to be explained.
    import os

    if os.environ.get('SEERDB_SPY') != '1':
        return
    import sys

    import seerdb.client.connection as cn
    import seerdb.client.cursor as cm

    def say(text):
        print('SPY', text, file=sys.stderr, flush=True)

    def wrap(cls, name, before):
        orig = getattr(cls, name)

        def call(self, *a, **kw):
            label = before(self, a, kw)
            try:
                out = orig(self, *a, **kw)
            except Exception as exc:
                say(f'{label} !! {str(exc).splitlines()[0][:90]}')
                raise
            rc = getattr(self, 'rowcount', None) if hasattr(self, 'rowcount') else None
            say(f'{label} ok' + (f' rowcount={rc}' if rc is not None else ''))
            return out

        setattr(cls, name, call)

    def conn_id(cursor):
        return f'k{id(cursor._connection) % 100000}'

    wrap(
        cm.Cursor,
        'execute',
        lambda s, a, k: f'{conn_id(s)} EXEC {" ".join(str(a[0]).split())[:110]}',
    )
    wrap(
        cm.Cursor,
        'executemany',
        lambda s, a, k: (
            f'{conn_id(s)} MANY n={len(a[1])} {" ".join(str(a[0]).split())[:100]}'
        ),
    )
    wrap(cn.OracleConnect, 'commit', lambda s, a, k: f'k{id(s) % 100000} COMMIT')
    wrap(cn.OracleConnect, 'rollback', lambda s, a, k: f'k{id(s) % 100000} ROLLBACK')
    wrap(cn.OracleConnect, 'close', lambda s, a, k: f'k{id(s) % 100000} CLOSE')
