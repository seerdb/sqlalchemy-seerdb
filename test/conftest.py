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

pytest.register_assert_rewrite('sqlalchemy.testing.assertions')

from sqlalchemy.testing.plugin.pytestplugin import *
