# SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
# SPDX-License-Identifier: MIT

"""Which parts of the compliance suite apply to this backend.

The suite assumes a capable backend and asks here about anything a particular
one may not do. Left at the defaults, features this backend simply does not have
are counted as **failures** rather than **skips**, which buries the real work
under noise.

Every entry below was checked against a live server rather than assumed, and
each says which it is: something the backend genuinely cannot do, or something
it can do that the suite is conservative about by default. Entries for our own
unfinished work do **not** belong here — a dialect gap is a bug to fix, and
silencing it here would hide it.
"""

from __future__ import annotations

from sqlalchemy.testing import exclusions
from sqlalchemy.testing.requirements import SuiteRequirements


class Requirements(SuiteRequirements):
    # --- things the backend genuinely does not have -----------------------

    @property
    def time(self):
        """No standalone time-of-day column type.

        `CREATE TABLE t (c TIME)` is rejected outright with "invalid datatype".
        A time of day is stored inside a date or timestamp instead, so the
        suite's TIME round-trips cannot apply.
        """
        return exclusions.closed()

    @property
    def time_microseconds(self):
        """Follows from there being no time type at all."""
        return exclusions.closed()

    @property
    def datetime_microseconds(self):
        """The plain date/time type has one-second resolution.

        Verified: a value carrying microseconds comes back with them zeroed,
        because that type has no sub-second component. The timestamp type does
        keep them — see below — so this is a property of the type the suite
        exercises here, not of the backend as a whole.
        """
        return exclusions.closed()

    # --- things it can do that the suite is conservative about ------------

    @property
    def timestamp_microseconds(self):
        """The timestamp type keeps sub-second precision.

        Off by default in the suite. Verified: a value with 123456 microseconds
        round-trips intact through a `TIMESTAMP(6)` column.
        """
        return exclusions.open()
