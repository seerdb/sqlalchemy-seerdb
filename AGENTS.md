<!--
SPDX-FileCopyrightText: 2026 Peter Lemenkov <lemenkov@gmail.com>
SPDX-License-Identifier: MIT
-->

# Notes for coding agents

This file collects repeatable procedures for automated / AI agents working
on `sqlalchemy-seerdb`. It mirrors the driver's own
[`AGENTS.md`](https://github.com/seerdb/seerdb/blob/master/AGENTS.md); the
driver's [`CONTRIBUTING.md`](https://github.com/seerdb/seerdb/blob/master/CONTRIBUTING.md)
states the project's clean-room posture, which applies here too even though
this package never touches the wire: it consumes seerdb's DB-API surface and
nothing below it.

## What this package is

A SQLAlchemy dialect, `oracle+seerdb://`, on top of the seerdb driver. Its
measure is SQLAlchemy's own dialect compliance suite (`test/test_suite.py`
imports it whole), run against live Oracle servers. The suite is a progress
report, not a gate: a run is read by its numbers and by *why* something fails,
never by green alone.

## Cutting a release

Releases publish to PyPI automatically via GitHub Actions Trusted Publishing,
triggered when the maintainer **pushes a version tag**. An agent's job is to
*prepare* the release on a branch and open the PR — never to merge or tag it.
The flow is the driver's, so the two repositories share one procedure:

1. **Branch off `master`**, named `release-x.y.z` (e.g. `release-0.2.0`).

2. **Bump the version in both places — they must stay in sync:**
   - `pyproject.toml` → `version = "x.y.z"`
   - `sqlalchemy_seerdb/__init__.py` → `__version__ = 'x.y.z'`

   `test/test_version.py` fails when they drift, and the packaging job runs
   it.

3. **Set the driver floor honestly.** If this release depends on driver fixes,
   raise `seerdb>=…` in `pyproject.toml`'s `dependencies` to the first seerdb
   release that carries them, and say which fixes in the commit message. A
   dialect release must never require an unreleased driver.

4. **Open a PR** against `master` titled `Release x.y.z`. In the body, state
   the validation status: which tiers the compliance suite passed on, against
   which released driver (the `latest` legs of the push run, or a run of the
   released-driver workflow pinned to that version), and any known failures
   with their tickets.

5. **Stop there. Do NOT merge the PR, and do NOT create or push the tag.** The
   maintainer reviews, merges, tags `x.y.z`, and the tag publishes through
   `release.yml`: a GitHub Release, then PyPI via Trusted Publishing from the
   `pypi` environment. PyPI has to know that publisher (owner `seerdb`,
   repository `sqlalchemy-seerdb`, workflow `release.yml`, environment
   `pypi`), registered once on the project's PyPI page, as a pending
   publisher before the first release.

### Versioning

Semantic versioning against the dialect's public surface: the URL scheme, the
connect arguments it derives, the SQLAlchemy types it maps, and its
`requirements.py` (what it claims the backend can do). A tighter driver floor
alone is a **patch**; a new capability the suite now exercises is a **minor**;
a change to what an existing URL or type does is a **major**.

## Running the compliance suite

```
pytest --dburi "oracle+seerdb://user:password@host:1521/?service_name=XE"
```

- `test.cfg` is mandatory and must stay: SQLAlchemy's pytest plugin reads it
  with `configparser`, not from `pyproject.toml`. Without it the whole module
  fails to collect.
- The suite needs a second schema named `test_schema` and a test user that can
  reach into it (see the README's "one setup step" and the grant list in
  `.github/workflows/compliance.yml`). Three environment traps found the hard
  way, each of which looks like a driver bug until it is not:
  - the test user's tables must live in the `USERS` tablespace, because the
    Oracle dialect hides `SYSTEM`-tablespace tables from reflection and the
    suite then never empties them between tests (rows "survive", ORA-00001);
  - the test user needs `SELECT ANY SEQUENCE`, or sequences in `test_schema`
    are invisible to reflection and get re-created (ORA-00955);
  - the recycle bin refills with every run and one test insists the default
    schema owns no sequences: purge it, or turn it off on a testbed.
- Run classes with `-k`, never whole-suite `-k` expressions with `%` in them
  (pytest mangles them), and add `-p no:randomly` when comparing two runs.
- `SEERDB_SPY=1` with `-s` prints one stderr line per execute, commit and
  rollback the driver receives, with the connection identity and rowcount
  (`test/conftest.py`). Use it when a failure will not reproduce locally: the
  suite swallows some of its own errors (the per-test DELETE among them) and
  prints them from a passing test's teardown, which pytest never shows.

### `requirements.py`

`sqlalchemy_seerdb/requirements.py` tells the suite what the backend can do.
Open a requirement only after verifying it live on the tier it claims; close
one with the reason in a comment. Gate on the server version through
`config.db.dialect.server_version_info` when a capability starts at a release
(identity columns and therefore `autoincrement_insert` start at 12c), so the
tests below it skip with the reason instead of failing. Never deselect tests
to make a run green.

## CI

Three workflows, one job definition:

- `compliance.yml` is reusable and takes `seerdb`: `latest` (the release a
  user installs, whatever the dependency floor resolves to on PyPI), `tag`
  (the driver's newest git tag, the same release without PyPI's index lag),
  `master` (the driver's git master) or a pinned release such as `2.5.0`.
- `tests.yml` calls it for `latest`, `tag` and `master` on every push and
  pull request: the first two are what the dialect is released against, the
  third is the early warning for the next driver release.
- `released.yml`, "SQLAlchemy vs released seerdb", runs it on demand from the
  Actions tab (version box, default `latest`) and weekly.
- `releases.yml`, "Releases (dialect tag vs seerdb tag)", pairs this
  repository's newest tag with the driver's newest tag, on demand and weekly:
  what a user gets who installs both releases. `compliance.yml`'s `dialect`
  input (`checkout` | `tag`) is what selects the dialect side.

Right after a driver release, a `latest` leg can fail with "no matching
distribution" while PyPI's index propagates; rerun it before reading anything
into it.
