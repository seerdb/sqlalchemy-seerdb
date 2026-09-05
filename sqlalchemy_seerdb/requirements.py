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

    @property
    def symbol_names_w_double_quote(self):
        """A double quote cannot appear in an identifier at all.

        Not a quoting bug on our side — the generated DDL is correct, doubling
        the inner quote the way SQL says to. The server rejects it anyway:

            CREATE TABLE "quote "" two" (...)
            ORA-25716: The identifier contains a double quotation mark (")

        A single quote in an identifier is fine, so this is specifically about
        the double quote.
        """
        return exclusions.closed()

    @property
    def expressions_against_unbounded_text(self):
        """An unbounded text column cannot appear in a WHERE clause.

        Verified: comparing one is refused outright.

            select 1 from t where clob_column = 'x'
            ORA-22848: cannot use CLOB type as comparison key

        Such a column has to be converted first, which is a different query
        from the one the suite writes, so these comparisons cannot apply.
        """
        return exclusions.closed()

    @property
    def empty_strings_varchar(self):
        """An empty string is not a value here — it is NULL.

        Verified: inserting `''` into a VARCHAR2 and reading it back gives NULL,
        and `v IS NULL` is true. This is the backend's own rule about the empty
        string, not a driver or dialect choice, so a test that round-trips one
        cannot apply.
        """
        return exclusions.closed()

    @property
    def empty_strings_text(self):
        """The same rule, verified separately on an unbounded text column."""
        return exclusions.closed()

    @property
    def unbounded_varchar(self):
        """A bounded character column must say how long it is.

            CREATE TABLE t (one VARCHAR2)
            ORA-00906: missing left parenthesis

        An unbounded *text* column is a different type and does work — see the
        CLOB round trips, which pass — so this is specifically about declaring a
        varchar with no length.
        """
        return exclusions.closed()

    @property
    def parens_in_union_contained_select_wo_limit_offset(self):
        """A parenthesised branch of a UNION cannot carry its own ORDER BY.

            (SELECT id FROM t ORDER BY id) UNION (SELECT id FROM t ORDER BY id)
            ORA-00907: missing right parenthesis

        SQLAlchemy's own requirement documents this as failing on this backend:
        without a LIMIT or OFFSET nothing wraps the branch in a subquery, and
        the bare form is a syntax error here.
        """
        return exclusions.closed()

    @property
    def parens_in_union_contained_select_w_limit_offset(self):
        """The same with a row limit, which is refused just as firmly.

        (SELECT ... ORDER BY id FETCH FIRST 1 ROWS ONLY) UNION (...)
        ORA-00900: invalid SQL statement
        """
        return exclusions.closed()

    # --- things it can do that the suite is conservative about ------------

    @property
    def temp_table_names(self):
        """Temporary tables can be listed by name.

        Off by default in the suite. This backend's temporary tables are
        *global*: the definition is a permanent, ordinary catalog entry — only
        the rows are session-private — so listing them is no different from
        listing any other table. Verified: a `CREATE GLOBAL TEMPORARY TABLE`
        appears in `user_tables` with `TEMPORARY = 'Y'`, and
        `Inspector.get_temp_table_names()` returns it, while `get_table_names()`
        correctly leaves it out.

        Saying so matters beyond the one test that asks directly. Left closed,
        the suite still *creates* its temporary table — that is governed by the
        separate `temp_table_reflection`, which is on — but then expects
        reflection not to mention it. Reflection here does mention it, correctly,
        and the disagreement was the single largest source of failures in the
        suite: 72 of them, across ten reflection tests that have nothing to do
        with temporary tables as such.
        """
        return exclusions.open()

    @property
    def has_temp_table(self):
        """A single temporary table can be checked by name.

        Follows from the above and verified the same way:
        `Inspector.has_table()` on a global temporary table returns True.
        """
        return exclusions.open()

    @property
    def views(self):
        """Views exist, so the suite may build its own and expect to see them.

        Off by default. Verified: a view created here is listed by
        `Inspector.get_view_names()` and its text comes back from
        `get_view_definition()`. Left closed, the fixture never creates the
        suite's views and `test_get_view_names` compares an empty list against
        the three names it expected to find.
        """
        return exclusions.open()

    @property
    def unique_constraints_reflect_as_index(self):
        """A UNIQUE constraint is backed by an index this backend creates for it,
        and reflection reports that index.

        Verified: `UniqueConstraint('u', name='v_parent_u_uq')` reflects through
        `get_indexes()` as `{'name': 'v_parent_u_uq', 'unique': True, ...}`.
        The suite's expected index sets include such entries only when this is
        declared, so left at the default every reflected unique constraint was
        an unexplained extra — the single largest group of remaining failures.

        A FOREIGN KEY, by contrast, gets no index here, so
        `foreign_keys_reflect_as_index` stays at its closed default. Also
        verified rather than assumed.
        """
        return exclusions.open()

    @property
    def reflect_indexes_with_ascdesc_as_expression(self):
        """A DESC column in an index reflects as an expression, not a column.

        Verified: `Index('ix', text('q DESC'))` comes back as
        `column_names: [None], expressions: ['"Q"'],
        column_sorting: {'"Q"': ('desc',)}`. That is the shape this requirement
        describes, and the shape the suite expects once it is declared.
        """
        return exclusions.open()

    @property
    def reflect_table_options(self):
        """Table options can be reflected.

        Verified: `get_table_options()` returns a dict, e.g.
        `{'oracle_tablespace': 'USERS'}`. Off by default the suite expects a
        `NotImplementedError` instead, and fails on "Callable did not raise".
        """
        return exclusions.open()

    @property
    def reflects_pk_names(self):
        """A primary-key constraint's name survives reflection.

        Verified: an unnamed key reflects as its system name (`sys_c0012860`) and
        an explicitly named one keeps that name. Off by default the suite treats
        the name check as expected-to-fail, and reports an "Unexpected success"
        when it passes.
        """
        return exclusions.open()

    @property
    def timestamp_microseconds(self):
        """The timestamp type keeps sub-second precision.

        Off by default in the suite. Verified: a value with 123456 microseconds
        round-trips intact through a `TIMESTAMP(6)` column.
        """
        return exclusions.open()
