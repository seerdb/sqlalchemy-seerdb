# SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT
"""The version lives in two places and they must agree."""

import re
import unittest
from pathlib import Path

import sqlalchemy_seerdb


class TestVersion(unittest.TestCase):
    def test_module_and_package_metadata_agree(self):
        pyproject = (
            Path(__file__).resolve().parent.parent / 'pyproject.toml'
        ).read_text()
        declared = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE).group(1)
        self.assertEqual(sqlalchemy_seerdb.__version__, declared)
