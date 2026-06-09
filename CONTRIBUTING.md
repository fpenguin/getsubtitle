# Contributing to GetSubtitle

Thanks for contributing. This file is the **how** (mechanics). For the
**what** and **why**, read these first:

1. `README.md` — what the tool does.
2. `AGENTS.md` — the rules (vocabulary, conventions, engineering contract).
3. `UX_PHILOSOPHY.md` — the reasoning behind the rules.

This file does not restate those principles; it covers setup, testing, and
the PR process.

## Development setup

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
# Editable install with dev tools + all reading-aid backends:
pip install -e ".[dev,furigana,romanization-ko,romanization-zh,romanization-yue]"
```

There is no `requirements.txt` — dependencies live in `pyproject.toml`
(`[project.optional-dependencies]`). The reading-aid extras
(`furigana`, `romanization-ko/-zh/-yue`) are optional, but install them so the
full suite runs the same way it does in CI.

## Running tests

```bash
python -m pytest tests/test_core.py -q
```

- **CI gates every PR.** `.github/workflows/ci.yml` runs this suite (plus a
  compile + help smoke) on Python 3.10 and 3.11. Your branch must be green.
- **Tests are config-isolated.** `tests/conftest.py` points
  `GETSUBTITLE_CONFIG_PATH` at an empty config so the suite never reads your
  real `~/.config/getsubtitle/user_settings.toml`. Do not remove this — without
  it, a personal config (e.g. `[merge] reading = true`) silently breaks merge
  tests on your machine but not in CI. A test that needs specific settings sets
  `GETSUBTITLE_CONFIG_PATH` itself, per test.
- **Verify on a clean state**, not on local generated files or uncommitted
  artifacts. If it only passes in your working tree, it isn't passing.

## Wizard changes

Wizard regressions are high priority — beginners hit them first.

- End-to-end behavior is pinned by golden transcripts in
  `tests/wizard_transcripts/`, driven by `tests/wizard_scenarios/*.py` via
  `tests/wizard_harness.py`.
- After an intentional wording/flow change, re-bless and **review the diff
  like a mini UX review**:
  ```bash
  WIZARD_UPDATE_SNAPSHOTS=1 python -m pytest tests/test_core.py -k wizard_scenario -q
  ```
- To report a wizard bug, add a failing scenario first.
- Check that default answers still work (Enter accepts the default; invalid
  input re-prompts rather than aborting).

## Error handling

User-facing failures must answer **what happened / why / what to do next**.
Raise `CliError(...)` for expected errors — the entry point turns it into a
one-line message and exit code 2. An uncaught exception (stack trace) reaching
a normal user workflow is a bug, not acceptable output.

## Testing philosophy

Tests protect CLI behavior, wizard behavior, user-facing output, and recovery
flows. Prefer adding a failing test *before* fixing a bug.

## Versioning

Pre-1.0: stay in the `v0.9.x` line; do not bump the version as a reflex. See
`ROADMAP.md` → "Versioning direction". `v1.0` is the marketing-ready debut.

## Documentation

Keep docs in sync with behavior. When you change behavior, update:

- `README.md` (user-facing behavior)
- `AGENTS.md` (only if agent guidance / a rule changes)
- `UX_PHILOSOPHY.md` (only if a UX principle changes)

Avoid duplicating the same fact across docs — duplication drifts. Volatile
facts (test counts, versions, commit hashes) do not belong in AGENTS.md or
UX_PHILOSOPHY.md.

## Pull requests

**Good PRs** solve one problem, include tests, and explain the user impact.

**Avoid:** large unrelated refactors; renaming established concepts
(Fetch / Translate / Modify / Merge / Rename); and mixing UX changes with
architecture changes in one PR.

When priorities conflict, use the order in `UX_PHILOSOPHY.md` →
"Priority order when principles conflict".
