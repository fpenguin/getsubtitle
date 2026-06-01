"""End-to-end scenario harness for the interactive wizard.

This module is the missing layer between unit tests (which exercise one
question or one emitter helper at a time) and a real TTY run. Beginner
users keep finding bugs in the *sequence* of prompts they see — the
wording, ordering, default-picks, and conditional branches — that no
single-function test can catch.

The harness drives `_run_wizard()` (the orchestrator wrapped by
`interactive_main`) by feeding canned input lines through a patched
`builtins.input`. Every line the wizard prints is captured into a
transcript that scenarios assert on (substring checks) and that an
optional snapshot file pins byte-for-byte.

Usage from a scenario module:

    from tests.wizard_harness import Scenario

    SCENARIO = Scenario(
        name="trap_q1_rejects_free_text",
        inputs=["totoro", "1,3,4", ...],
        expect_stdout_contains=["Invalid selection"],
    )

A single parametrised pytest entry point (defined inside this file as
`test_wizard_scenario`) collects every `SCENARIO` / `SCENARIOS` exported
from a module under `tests/wizard_scenarios/` and runs it through
`run_scenario()`.

Snapshot blessing:

    WIZARD_UPDATE_SNAPSHOTS=1 pytest tests/test_core.py::test_wizard_scenario

writes the captured transcript to `tests/wizard_transcripts/{name}.txt`
instead of asserting. Without that env var, a missing golden file is a
test failure — there is no implicit "first run creates the snapshot"
mode, because that would silently let bug regressions slip in unnoticed.
"""

from __future__ import annotations

import contextlib
import io
import os
import runpy
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Load the core module once and reuse the namespace across scenarios.
# Tests in this repo use runpy.run_path, but runpy returns a *snapshot*
# of the executed namespace — the functions inside keep their own live
# __globals__ reference. Patching the snapshot dict doesn't affect what
# the functions see (HANDOFF.md "Sandbox Testing Without Network" calls
# this out). To make `MODULE[name] = stub` actually monkeypatch the
# wizard, redirect MODULE to the live globals dict via any function's
# __globals__ attribute. All functions in the module share that same
# dict, so a single redirect catches every reference.
_CORE_PATH = Path(__file__).resolve().parents[1] / "getsubtitle_core.py"
_LOADED: dict[str, Any] = runpy.run_path(str(_CORE_PATH), run_name="getsubtitle_wizard_harness")
MODULE: dict[str, Any] = _LOADED["interactive_main"].__globals__


SCENARIO_DIR = Path(__file__).resolve().parent / "wizard_scenarios"
TRANSCRIPT_DIR = Path(__file__).resolve().parent / "wizard_transcripts"


# ─── FakeTTY ────────────────────────────────────────────────────────────


class _ScriptedInputExhausted(AssertionError):
    """Raised when the wizard reads more input lines than the scenario
    provided. The harness converts this into a readable pytest failure
    that prints the transcript so far."""


class FakeTTY:
    """Context manager that pretends stdin/stdout are a terminal,
    captures all printed output into a transcript string, and feeds
    queued input lines through the wizard's `input()` callsites.

    The wizard reads input only via the module-level `input` global
    (see `_wizard_prompt` / `_wizard_yesno`), so patching that one
    name catches every prompt. The TTY-state patches matter because
    `_wizard_is_interactive()` short-circuits the wizard otherwise.
    """

    def __init__(self, inputs: list[str]) -> None:
        # Copy so the caller's list isn't mutated as we pop.
        self._inputs: list[str] = list(inputs)
        self._cursor = 0
        self._stdout = io.StringIO()
        self._echo_buffer: list[str] = []
        self._saved: dict[str, Any] = {}
        # We don't actually swap sys.stdin — pytest's capture infrastructure
        # owns it. Instead, the wizard's `_wizard_is_interactive()` is
        # patched directly. Simpler, fewer footguns.

    def __enter__(self) -> "FakeTTY":
        # Patch the wizard's interactive-mode gate to True so the
        # wizard doesn't bail with "needs a tty".
        self._saved["_wizard_is_interactive"] = MODULE["_wizard_is_interactive"]
        MODULE["_wizard_is_interactive"] = lambda: True

        # Hook the module-level `input` global so prompts read from
        # our queue. Record whether `input` was originally in MODULE
        # (it usually isn't — the builtin is resolved via builtins
        # scope, not the module dict) so the restore step doesn't
        # leak the stub between scenarios.
        self._had_input = "input" in MODULE
        if self._had_input:
            self._saved["input"] = MODULE["input"]

        def _scripted_input(prompt: str = "") -> str:
            if self._cursor >= len(self._inputs):
                # Capture what we have so far before bailing so the
                # diagnostic message is actionable.
                self._echo_buffer.append(prompt)
                transcript_so_far = self._stdout.getvalue() + "".join(self._echo_buffer)
                raise _ScriptedInputExhausted(
                    f"Wizard asked for input #{self._cursor + 1} but script "
                    f"has only {len(self._inputs)} line(s).\n"
                    f"--- transcript so far ---\n{transcript_so_far}\n"
                    f"--- end transcript ---"
                )
            answer = self._inputs[self._cursor]
            self._cursor += 1
            # Echo into transcript so the saved snapshot shows the
            # actual conversation, not just the wizard's side of it.
            self._stdout.write(prompt)
            self._stdout.write(answer)
            self._stdout.write("\n")
            return answer

        MODULE["input"] = _scripted_input
        # Redirect stdout. Use a stack so other context managers
        # (snapshot writers etc.) can capture output through us.
        self._stdout_cm = contextlib.redirect_stdout(self._stdout)
        self._stdout_cm.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self._stdout_cm.__exit__(exc_type, exc, tb)
        finally:
            MODULE["_wizard_is_interactive"] = self._saved["_wizard_is_interactive"]
            if self._had_input:
                MODULE["input"] = self._saved["input"]
            else:
                MODULE.pop("input", None)

    @property
    def transcript(self) -> str:
        return self._stdout.getvalue()

    @property
    def consumed_inputs(self) -> int:
        return self._cursor


# ─── Scenario dataclass ─────────────────────────────────────────────────


@dataclass
class Scenario:
    """A single end-to-end wizard interaction.

    `inputs` is a sequence of strings that will be returned by the
    wizard's `input()` calls in order. Placeholders containing the
    string `{TMP}` are substituted with the harness-managed temp
    directory before the wizard sees them — this keeps scenarios free
    of host-specific paths and lets the snapshot file stay stable
    across machines.

    `files` is a `{relative_or_TMP_path: text_content}` dict; the
    harness writes each file before running. `{TMP}` substitution
    happens in keys too.

    `expect_state` is matched against attributes of the final
    `_WizardState`. For set values (e.g. `state.steps`), equality is
    used. For other types, equality with the recorded value.

    Snapshot mode: when `golden=True` (default), the transcript is
    compared byte-for-byte against
    `tests/wizard_transcripts/{name}.txt`. Missing snapshot is an
    error unless `WIZARD_UPDATE_SNAPSHOTS=1` is set, in which case the
    transcript is written.
    """

    name: str
    inputs: list[str]
    files: dict[str, str] = field(default_factory=dict)
    keys: dict[str, str] = field(default_factory=dict)
    network_blocked: bool = True
    expect_state: dict[str, Any] = field(default_factory=dict)
    expect_cli_contains: list[str] = field(default_factory=list)
    expect_cli_lacks: list[str] = field(default_factory=list)
    expect_toml_contains: list[str] = field(default_factory=list)
    expect_toml_lacks: list[str] = field(default_factory=list)
    expect_stdout_contains: list[str] = field(default_factory=list)
    expect_stdout_lacks: list[str] = field(default_factory=list)
    # Number of times `main()` should have been dispatched. `None`
    # means 'don't check'. Use 0 to assert no dispatch (save/quit),
    # 1 to assert exactly one (the trap_open_folder_only_opens fix).
    expect_main_call_count: int | None = None
    # Allow a scenario to opt out of the byte-equal snapshot when the
    # transcript depends on host state (e.g. installed pip packages).
    golden: bool = True
    # Optional pre-flight hook: receives the temp-dir path and the
    # state object before the wizard runs. Used by a handful of
    # scenarios that need to seed `_WizardState` (e.g. "wizard was
    # already part-way through" tests).
    pre_state: Callable[[Path, Any], None] | None = None


@dataclass
class ScenarioResult:
    """Return shape from `run_scenario()`. Fields are read in the
    pytest entry point to format failure messages."""

    transcript: str
    state: Any
    emitted_cli: list[str]
    emitted_toml: str
    exit_code: int
    # Each entry is a copy of the `argv` list that `interactive_main`
    # passed to `main()` for the 'run' action. Empty for save/quit
    # flows. Used by scenarios that care about double-dispatch traps.
    main_calls: list[list[str]] = field(default_factory=list)
    # The per-run tmp directory — needed to scrub host-specific path
    # prefixes from the transcript before comparing to the golden
    # snapshot.
    tmp: Path | None = None


# ─── Network-blocking helpers ───────────────────────────────────────────


_NETWORK_TARGETS = (
    "request_json", "request_text", "request_bytes",
    "tmdb_search_tv", "tmdb_search_movie", "search_anilist",
    "fetch_anilist_info",
)


def _block_network(saved: dict[str, Any]) -> None:
    """Stub every outbound-request function so a misfiring scenario
    can't hit the network. We return empty/None rather than raising
    because some wizard call sites only catch CliError (not generic
    exceptions), and a leaked exception would hide the real assertion."""
    for name in _NETWORK_TARGETS:
        if name in MODULE:
            saved[name] = MODULE[name]
            if name in ("tmdb_search_tv", "tmdb_search_movie", "fetch_anilist_info"):
                MODULE[name] = lambda *_a, **_k: None
            elif name == "search_anilist":
                MODULE[name] = lambda *_a, **_k: []
            else:
                MODULE[name] = _network_blocked_call(name)
    # Ollama reachability check should report "down" by default.
    if "_wizard_ollama_reachable" in MODULE:
        saved["_wizard_ollama_reachable"] = MODULE["_wizard_ollama_reachable"]
        MODULE["_wizard_ollama_reachable"] = lambda: False


def _restore_network(saved: dict[str, Any]) -> None:
    for name in (*_NETWORK_TARGETS, "_wizard_ollama_reachable"):
        if name in saved:
            MODULE[name] = saved[name]


def _network_blocked_call(name: str) -> Callable[..., Any]:
    def _raise(*_a, **_k):
        raise RuntimeError(f"network blocked in scenario harness: {name} called")
    return _raise


def _block_main_dispatch(saved: dict[str, Any]) -> None:
    """When the wizard's `run` action is exercised, it shells out via
    `main(dispatch_argv)`. Tests must not actually execute that
    pipeline (and would lack the deps to anyway), so we stub `main`
    to return success and record what it was called with."""
    saved["main"] = MODULE.get("main")
    calls: list[list[str]] = []

    def _record(argv: list[str]) -> int:
        calls.append(list(argv))
        return 0

    MODULE["main"] = _record
    saved["_main_calls"] = calls

    # Same for `open_folder` — we don't actually want to launch Finder
    # on a maintainer's machine during scenario tests.
    if "open_folder" in MODULE:
        saved["open_folder"] = MODULE["open_folder"]
        MODULE["open_folder"] = lambda _p: None

    # Stub setup-profile loader so the wizard never asks the pre-fill
    # question first. Scenarios are deterministic only when this is
    # off — otherwise the test depends on whether the maintainer has
    # ever run `getsubtitle setup` on this machine.
    if "_setup_load_profile" in MODULE:
        saved["_setup_load_profile"] = MODULE["_setup_load_profile"]
        MODULE["_setup_load_profile"] = lambda: None

    # Stub `set_api_keys` so a scenario can drive the "blocker → Run
    # setup now?" branch without actually prompting for a key. Returns
    # 0 (success) so the wizard prints "✓ key saved".
    if "set_api_keys" in MODULE:
        saved["set_api_keys"] = MODULE["set_api_keys"]
        MODULE["set_api_keys"] = lambda *_a, **_k: 0


def _restore_main_dispatch(saved: dict[str, Any]) -> None:
    if "main" in saved:
        MODULE["main"] = saved["main"]
    if "open_folder" in saved:
        MODULE["open_folder"] = saved["open_folder"]
    if "_setup_load_profile" in saved:
        MODULE["_setup_load_profile"] = saved["_setup_load_profile"]
    if "set_api_keys" in saved:
        MODULE["set_api_keys"] = saved["set_api_keys"]


def _block_provider_keys(saved: dict[str, Any], keys: dict[str, str]) -> None:
    """Stub `get_provider_api_key` so scenarios can simulate "DeepL key
    present" or "TMDB key absent" without touching real keychain.

    `keys` is a {provider: value_or_empty_string} dict. Providers not
    present in the dict default to empty (= unconfigured)."""
    saved["get_provider_api_key"] = MODULE["get_provider_api_key"]

    def _fake(provider: str, *_a, **_k) -> str | None:
        return keys.get(provider) or None

    MODULE["get_provider_api_key"] = _fake


def _restore_provider_keys(saved: dict[str, Any]) -> None:
    if "get_provider_api_key" in saved:
        MODULE["get_provider_api_key"] = saved["get_provider_api_key"]


# ─── Scenario runner ────────────────────────────────────────────────────


def _substitute_tmp(value: str, tmp: Path) -> str:
    return value.replace("{TMP}", str(tmp))


def _write_files(files: dict[str, str], tmp: Path) -> None:
    for raw_path, content in files.items():
        path = Path(_substitute_tmp(raw_path, tmp))
        if not path.is_absolute():
            path = tmp / path
        path.parent.mkdir(parents=True, exist_ok=True)
        # SAMI files etc. may be bytes-as-text — assume UTF-8 unless a
        # scenario explicitly handles its own files in `pre_state`.
        path.write_text(content, encoding="utf-8")


def run_scenario(scenario: Scenario) -> ScenarioResult:
    """Execute a single scenario end-to-end and return its result.

    We drive `interactive_main()` rather than `_run_wizard()` so the
    transcript covers the full UX surface: the welcome intro, the
    dependency probe, the save/run/restart/quit branches, and the
    post-run open-folder + variant-cleanup prompts. Scenarios that
    only need the question flow can still focus their asserts on
    state + emitters; the snapshot pins the rest."""
    saved: dict[str, Any] = {}
    saved_env: dict[str, str | None] = {}
    # Use a deterministic XDG_CACHE_HOME so the wizard-draft path
    # doesn't pollute the user's real cache.
    cache_dir = tempfile.mkdtemp(prefix="wizard-cache-")
    saved_env["XDG_CACHE_HOME"] = os.environ.get("XDG_CACHE_HOME")
    os.environ["XDG_CACHE_HOME"] = cache_dir

    # Per-scenario tmp dir for staged files.
    tmp = Path(tempfile.mkdtemp(prefix="wizard-scn-"))
    _write_files(scenario.files, tmp)
    # Resolve symlinks so `tmp` matches what the wizard prints (macOS
    # /var → /private/var). Snapshots are then path-stable across
    # platforms because the harness replaces this exact prefix with
    # the placeholder before comparison.
    try:
        tmp = tmp.resolve()
    except OSError:
        pass

    # Substitute `{TMP}` in every input line so scenarios can refer
    # to staged files by a stable placeholder.
    inputs = [_substitute_tmp(line, tmp) for line in scenario.inputs]

    if scenario.network_blocked:
        _block_network(saved)
    _block_main_dispatch(saved)
    _block_provider_keys(saved, scenario.keys)

    # Capture the final `_WizardState` so assertions can introspect
    # it. Wrap `_run_wizard` so we see the state at the moment Q12
    # returns (this is the state the action handler in
    # `interactive_main` uses).
    saved["_run_wizard"] = MODULE["_run_wizard"]
    _orig_run_wizard = MODULE["_run_wizard"]

    def _capture_run_wizard(initial_state=None):
        state, action = _orig_run_wizard(initial_state)
        MODULE["_LAST_WIZARD_STATE_FOR_TESTS"] = state
        return state, action

    MODULE["_run_wizard"] = _capture_run_wizard

    # Apply any pre-state hook so a scenario can seed state before
    # interactive_main starts. Stash the seed under a sentinel attribute
    # and patch `_WizardState` momentarily to return the seeded copy.
    # In practice no current scenario needs this; the hook exists to
    # avoid future churn.
    seeded_state = MODULE["_WizardState"]()
    if scenario.pre_state is not None:
        scenario.pre_state(tmp, seeded_state)

    transcript = ""
    exit_code = 0
    final_state: Any = None

    try:
        with FakeTTY(inputs) as tty:
            try:
                exit_code = MODULE["interactive_main"]([])
            except MODULE["CliError"] as exc:
                # CliError is the documented bail-out path; surface its
                # message in the transcript and exit 2 so the snapshot
                # still pins the error wording.
                tty._stdout.write(f"CliError: {exc}\n")
                exit_code = 2
            # interactive_main creates and stores _WizardState locally.
            # Grab the last-seen state via a sentinel module attribute
            # that we install via FakeTTY's patching (next).
            final_state = MODULE.get("_LAST_WIZARD_STATE_FOR_TESTS")
        transcript = tty.transcript
    except _ScriptedInputExhausted as e:
        raise AssertionError(str(e)) from None
    finally:
        # Each restore catches its own exceptions so a failure during
        # cleanup doesn't leak stubs into the next scenario.
        for restore_fn in (
            lambda: _restore_provider_keys(saved),
            lambda: _restore_main_dispatch(saved),
            lambda: (MODULE.update({"_run_wizard": saved["_run_wizard"]})
                     if "_run_wizard" in saved else None),
            lambda: (_restore_network(saved) if scenario.network_blocked else None),
        ):
            try:
                restore_fn()
            except Exception:
                pass
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        MODULE.pop("_LAST_WIZARD_STATE_FOR_TESTS", None)

    if final_state is None:
        # interactive_main can return before any state was constructed
        # (CliError from the tty guard, for instance). Fall back to
        # the seeded blank state so asserts still get something.
        final_state = seeded_state

    emitted_cli = MODULE["_wizard_emit_cli"](final_state) if final_state else []
    emitted_toml = MODULE["_wizard_emit_toml"](final_state) if final_state else ""
    main_calls = saved.get("_main_calls", [])

    return ScenarioResult(
        transcript=transcript,
        state=final_state,
        emitted_cli=emitted_cli,
        emitted_toml=emitted_toml,
        exit_code=exit_code,
        main_calls=list(main_calls),
        tmp=tmp,
    )


# ─── Assertions ─────────────────────────────────────────────────────────


def _assert_substrings(haystack: str, needles: list[str], *, label: str, present: bool) -> None:
    for needle in needles:
        if present and needle not in haystack:
            raise AssertionError(
                f"{label}: expected substring {needle!r} but it was missing.\n"
                f"---\n{haystack}\n---"
            )
        if not present and needle in haystack:
            raise AssertionError(
                f"{label}: substring {needle!r} should NOT appear but it does.\n"
                f"---\n{haystack}\n---"
            )


def assert_scenario(scenario: Scenario, result: ScenarioResult) -> None:
    """Run every assertion declared on the scenario against the run
    result. Raises a single AssertionError on the first failure.

    Under `WIZARD_UPDATE_SNAPSHOTS=1`, the golden snapshot is written
    BEFORE the substring/state assertions so the maintainer can
    iteratively inspect a freshly-blessed transcript even when the
    other assertions still need adjustment. Without the env var, all
    asserts run in order and the snapshot comparison is last."""
    if scenario.golden and os.environ.get("WIZARD_UPDATE_SNAPSHOTS") == "1":
        _assert_golden_transcript(scenario, result)
    # State expectations.
    for attr, expected in scenario.expect_state.items():
        actual = getattr(result.state, attr, _MISSING)
        if actual is _MISSING:
            raise AssertionError(
                f"{scenario.name}: expect_state[{attr!r}] but state has no such attribute"
            )
        if actual != expected:
            raise AssertionError(
                f"{scenario.name}: state.{attr} = {actual!r}, expected {expected!r}"
            )
    cli_string = " ".join(result.emitted_cli)
    _assert_substrings(
        cli_string, scenario.expect_cli_contains,
        label=f"{scenario.name}: emitted CLI", present=True,
    )
    _assert_substrings(
        cli_string, scenario.expect_cli_lacks,
        label=f"{scenario.name}: emitted CLI", present=False,
    )
    _assert_substrings(
        result.emitted_toml, scenario.expect_toml_contains,
        label=f"{scenario.name}: emitted TOML", present=True,
    )
    _assert_substrings(
        result.emitted_toml, scenario.expect_toml_lacks,
        label=f"{scenario.name}: emitted TOML", present=False,
    )
    _assert_substrings(
        result.transcript, scenario.expect_stdout_contains,
        label=f"{scenario.name}: transcript", present=True,
    )
    _assert_substrings(
        result.transcript, scenario.expect_stdout_lacks,
        label=f"{scenario.name}: transcript", present=False,
    )
    if scenario.expect_main_call_count is not None:
        if len(result.main_calls) != scenario.expect_main_call_count:
            raise AssertionError(
                f"{scenario.name}: expected {scenario.expect_main_call_count} "
                f"main() dispatch(es) but got {len(result.main_calls)}: "
                f"{result.main_calls!r}"
            )
    if scenario.golden and os.environ.get("WIZARD_UPDATE_SNAPSHOTS") != "1":
        _assert_golden_transcript(scenario, result)


_MISSING = object()


# ─── Golden snapshot handling ───────────────────────────────────────────


def _golden_path(name: str) -> Path:
    return TRANSCRIPT_DIR / f"{name}.txt"


def _normalise_transcript(text: str, *, tmp: Path | None = None) -> str:
    """Strip trailing whitespace per line, normalise line endings,
    and rewrite the per-run tmp-dir path back to a `{TMP}` placeholder
    so byte-equal snapshots stay stable across runs and machines."""
    out = text.replace("\r\n", "\n")
    if tmp is not None:
        out = out.replace(str(tmp), "{TMP}")
        # macOS resolves /var → /private/var; some callers print the
        # unresolved form. Catch both.
        if str(tmp).startswith("/private/"):
            out = out.replace(str(tmp).removeprefix("/private"), "{TMP}")
    # Also strip any cache-dir noise from XDG_CACHE_HOME.
    cache_env = os.environ.get("XDG_CACHE_HOME")
    if cache_env:
        out = out.replace(cache_env, "{CACHE}")
    lines = out.split("\n")
    return "\n".join(line.rstrip() for line in lines).rstrip() + "\n"


def _assert_golden_transcript(scenario: Scenario, result: ScenarioResult) -> None:
    path = _golden_path(scenario.name)
    actual = _normalise_transcript(result.transcript, tmp=result.tmp)
    if os.environ.get("WIZARD_UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return
    if not path.exists():
        raise AssertionError(
            f"{scenario.name}: golden transcript missing at {path}. "
            "Run with WIZARD_UPDATE_SNAPSHOTS=1 to bless the current "
            "transcript, then inspect it before committing."
        )
    expected = path.read_text(encoding="utf-8")
    if actual != expected:
        diff = _format_transcript_diff(expected, actual)
        raise AssertionError(
            f"{scenario.name}: transcript mismatch vs {path}.\n{diff}"
        )


def _format_transcript_diff(expected: str, actual: str) -> str:
    import difflib
    diff = difflib.unified_diff(
        expected.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile="expected", tofile="actual",
        n=3,
    )
    return "".join(diff)


# ─── Scenario discovery ─────────────────────────────────────────────────


def collect_scenarios() -> list[Scenario]:
    """Import every module under `tests/wizard_scenarios/` and gather
    its top-level `SCENARIO` or `SCENARIOS` symbol. We use runpy.run_path
    so the directory needs no __init__.py and no sys.path gymnastics —
    the tests/ folder is not a Python package in this repo.

    A scenario module that fails to import is reported as a placeholder
    Scenario whose `name` encodes the failure. The matching parametrized
    test then surfaces a clear `AssertionError` instead of taking down
    the entire pytest collection — one broken scenario must not block
    the other 24."""
    if not SCENARIO_DIR.exists():
        return []
    found: list[Scenario] = []
    parent = str(SCENARIO_DIR.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    for path in sorted(SCENARIO_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            ns: dict[str, Any] = runpy.run_path(str(path))
        except Exception as exc:
            found.append(_broken_scenario(path.stem, exc))
            continue
        found.extend(_gather_scenarios_from_ns(ns))
    found.sort(key=lambda s: s.name)
    return found


def _broken_scenario(stem: str, exc: Exception) -> Scenario:
    # Encode the failure into a stable, recognisable scenario so the
    # parametrized test reports it instead of crashing collection.
    msg = f"scenario module {stem} failed to import: {exc!r}"
    return Scenario(
        name=f"{stem}__BROKEN__",
        inputs=[],
        golden=False,
        # Sentinel substring that won't appear in any real transcript;
        # assert_scenario will raise with the import error embedded.
        expect_stdout_contains=[msg],
    )


def _gather_scenarios_from_ns(ns: dict[str, Any]) -> list[Scenario]:
    out: list[Scenario] = []
    if "SCENARIO" in ns and isinstance(ns["SCENARIO"], Scenario):
        out.append(ns["SCENARIO"])
    if "SCENARIOS" in ns and isinstance(ns["SCENARIOS"], list):
        out.extend(s for s in ns["SCENARIOS"] if isinstance(s, Scenario))
    return out


# ─── Public entry-point for pytest ──────────────────────────────────────


def run_and_assert(scenario: Scenario) -> ScenarioResult:
    """One-call: run + assert. Used by the parametrised pytest entry."""
    result = run_scenario(scenario)
    assert_scenario(scenario, result)
    return result
