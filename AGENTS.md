# GetSubtitle — AI Agent Instructions

Project-specific guidance for AI coding agents (CODEX, Claude Code, Gemini
CLI, OpenHands, Aider, and future tools). **Read `README.md` first** for what
the tool does and how users run it.

## Which doc to read

| File | What it is | Changes |
|---|---|---|
| `AGENTS.md` (this file) | Durable product philosophy + engineering contract (the rules). Read every session. | Rarely |
| `UX_PHILOSOPHY.md` | The reasoning behind the UX rules (the *why*). | Rarely |
| `CONTRIBUTING.md` | Dev mechanics: setup, tests, re-bless, CI, PR process. | Rarely |
| `ARCHITECTURE.md` | Code map: dispatch, pipeline, layers, where things live. | Rarely |
| `README.md` | User-facing docs (install, commands, formats). | With features |
| `ROADMAP.md` | What's shipped / planned; pre-1.0 versioning policy. | With releases |
| `HANDOFF.md` / `CLAUDE.md` | Private local notes (gitignored): current baseline, session state, deep wizard internals. May be absent on a fresh clone. | Often |

Keep volatile facts (test counts, commit hashes, version numbers) **out of
this file** — they belong in HANDOFF.md and go stale fast. AGENTS.md is for
things that stay true.

## Project goal

GetSubtitle helps users (1) find subtitles, (2) fill missing languages,
(3) clean subtitles, (4) add reading aids, and (5) merge multiple languages
into language-learning subtitle workflows. It serves **CLI power users** and
**first-time users** via an interactive onboarding wizard equally.

## Core philosophy

**Human subtitles first.** Always prefer human-created subtitles; machine
translation is a *fallback* that fills missing languages only. Never redesign
workflows around MT being the primary source.

```text
Fetch     → human subtitles
Translate → fill missing languages only
```

**Beginner-first UX.** The wizard and setup flow target language learners,
anime fans, Plex users, and non-technical people. Prefer examples, outcomes,
and concrete language; avoid jargon, implementation details, and internal
terminology.

**Progressive disclosure.** Show: (1) outcome, (2) recovery action, (3)
technical details on request.

```text
Bad:   Provider timeout / HTTP 429 / Retry count 4 / Search provider failed
Good:  Could not search for subtitles.
       Retry in a few minutes.
       Show technical details? [y/N]
```

## Product vocabulary — do not rename

These five verbs are intentional and shared by the CLI and the wizard:

```text
Fetch   Translate   Modify   Merge   Rename
```

Do **not** replace them with "Download / Create Study Subtitles / Improve /
Combine" or other simplified labels. The wizard teaches the same concepts the
CLI uses.

## Workflow model

Most workflows are combinations of the verbs — preserve this mental model:

```text
Fetch + Merge
Fetch + Modify + Merge
Fetch + Translate + Modify + Merge
Modify only
Rename only
```

## Reading aids

Optional overlays that **do not replace** the original subtitle text. Always
illustrate with a real example rather than a technical explanation:

```text
Japanese  勉強する      → べんきょうする
Korean    한국어 공부    → hangugeo gongbu
Chinese   学中文        → xué zhōngwén
```

## Output formats — none is universally superior

Each format exists for a reason. Show the **real format name** with a
compatibility note; never hide formats behind generic labels like "Best for
TV".

- **SRT** — best compatibility. Plex, Jellyfin, smart TVs, tablets, phones, VLC.
- **ASS** — best local-study format. mpv, VLC, desktop, multi-language layouts,
  Korean/Chinese reading aids.
- **VTT** — best browser-study format. asbplayer, Netflix/Disney+/YouTube,
  browser learning. *Not* a universal recommendation.

## UX writing rules

Users care about outcomes, not internals.

```text
Prefer:  Downloaded: 2 subtitle files
Over:    Fetch: planned 2, wrote 2

Prefer:  Created: 1 merged subtitle file
Over:    Merge: scanned 2, planned 1, wrote 1
```

**Failures must answer What / Why / How-to-fix**, and distinct situations get
distinct recovery advice — never collapse them into one generic error:

```text
No subtitles exist     → No subtitles found.
Provider failure       → Could not search for subtitles.
Rate limiting          → Search temporarily unavailable. Try again in a few minutes.
Metadata mismatch      → Try searching with an alternate title.
```

Setup recommendations should explain **why** ("You selected anime and Japanese
learning"), not just **what** ("Jimaku is recommended").

## Working in this repo (engineering contract)

- **Single-file core.** `getsubtitle_core.py` is large (~22k lines) by design.
  Don't split it — the test suite imports the public surface from
  `getsubtitle_core`. Grep to navigate. `getsubtitle.py` is the console entry.
- **Run tests** with the project venv; keep the suite green before finishing:
  ```sh
  .venv/bin/python -m pytest tests/test_core.py -q
  ```
- **No tracebacks for expected errors.** Raise `CliError(...)`; the entry point
  turns it into a one-line stderr message and exit code 2. An uncaught
  exception reaching the user is a bug.
- **Interactive wizard menus** go through the one primitive
  `_wizard_read_choice(...)`: Enter → default, invalid → re-prompt (never
  abort, never silently default), `q` quits, `b` backs. Don't hand-roll menu
  input. Menu answers are numbers; reserve free text for languages/paths/URLs/
  titles/season-episode.
- **Wizard scenario harness.** End-to-end wizard behavior is pinned by golden
  transcripts in `tests/wizard_transcripts/`, driven by
  `tests/wizard_scenarios/*.py` via `tests/wizard_harness.py`. After an
  intentional wording/flow change, re-bless and review the diff like a mini UX
  review:
  ```sh
  WIZARD_UPDATE_SNAPSHOTS=1 .venv/bin/python -m pytest tests/test_core.py -k wizard_scenario -q
  ```
  To report a wizard bug, add a failing scenario first.
- **Pre-1.0 versioning.** Stay in `v0.9.x`; do not bump version as a reflex.
  See ROADMAP.md "Versioning direction". `v1.0` is the marketing-ready debut.
- **Don't bypass access controls.** No DRM/login/region circumvention; only
  handle subtitles the user can already access.

## Contributor rules

**Good:** improve clarity; reduce cognitive load; improve failure recovery;
add examples; improve scanability and onboarding.

**Avoid:** renaming workflow concepts; hiding advanced functionality;
replacing examples with abstractions; marketing language; *unnecessary*
confirmations. (Necessary safety gates — e.g. the Rename copy-vs-original
prompt — must stay.)

## Preferred design direction

When uncertain, prefer **short, clear, example-driven, actionable** over
**technical, verbose, implementation-focused**. The project should feel like a
helpful guide, not a debugging console.

> The reasoning behind these rules — plus user personas and the priority
> order when principles conflict — lives in `UX_PHILOSOPHY.md`. Keep this
> file short enough that agents read all of it every session.
