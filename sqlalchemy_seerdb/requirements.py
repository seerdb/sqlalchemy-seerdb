# SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT

"""Which parts of the compliance suite apply to this dialect.

Starts from the stock requirements; exclusions get added here as the suite is
brought up, each with a note saying whether it is a dialect gap or something the
server genuinely does not do.
"""

from sqlalchemy.testing.requirements import SuiteRequirements


class Requirements(SuiteRequirements):
    pass
