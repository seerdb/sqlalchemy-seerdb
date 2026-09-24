# SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT

"""A Boolean column comes back as a bool whatever the driver returns."""

import unittest

from sqlalchemy import types as sqltypes

from sqlalchemy_seerdb.seerdb import SeerdbDialect, _SeerdbBoolean


class TestBoolean(unittest.TestCase):
    def setUp(self):
        self.process = _SeerdbBoolean().result_processor(SeerdbDialect(), None)

    def test_a_number_becomes_a_bool(self):
        # Before 23ai the column is a NUMBER, and the driver reads 1 / 0.
        self.assertIs(self.process(1), True)
        self.assertIs(self.process(0), False)

    def test_a_native_bool_and_a_null_pass_through(self):
        self.assertIs(self.process(True), True)
        self.assertIs(self.process(False), False)
        self.assertIsNone(self.process(None))

    def test_the_dialect_uses_it_for_boolean(self):
        self.assertIs(SeerdbDialect.colspecs[sqltypes.Boolean], _SeerdbBoolean)


if __name__ == '__main__':
    unittest.main()
