# SPDX-FileCopyrightText: 2025 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT
"""The connect arguments the dialect derives from a URL."""

import unittest

from sqlalchemy.engine import make_url

from sqlalchemy_seerdb.seerdb import SeerdbDialect


def _options(url):
    _args, options = SeerdbDialect().create_connect_args(make_url(url))
    return options


class TestAutocommit(unittest.TestCase):
    """The driver commits every statement by default; SQLAlchemy must not.

    With the driver's default a transaction's rollback undid nothing, which
    the compliance suite noticed as rows surviving from one test into the
    next.
    """

    def test_off_by_default(self):
        options = _options('oracle+seerdb://u:p@h:1521/?service_name=s')
        self.assertIs(options['autocommit'], False)

    def test_the_url_can_turn_it_on(self):
        options = _options('oracle+seerdb://u:p@h:1521/?service_name=s&autocommit=true')
        self.assertIs(options['autocommit'], True)
