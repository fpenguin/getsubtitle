"""Persona: user picks DeepL but has no DeepL API key configured.

The dependency probe must classify this as a `block` row, surface a
one-line fix (`getsubtitle --set-key deepl`), and offer to call it
on the spot. If the user declines setup, the wizard must not dispatch
a doomed run; it should save the workflow for later."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_no_key_deepl",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    keys={},  # no deepl key
    inputs=[
        "2,3,4",        # translate + modify + merge (so probe sees deepl + we get a local source)
        "{TMP}/Show",   # path
        "ja,en",
        "4",            # translate engine: DeepL
        "1",            # reading aids — skip
        "",             # final format → recommended SRT
        "",             # font size → Regular
        "1",            # action: run (so probe fires)
        "y",            # accept 'Run setup now to fix these?'
        "n",            # at the per-gap prompt: don't actually run --set-key now
        "y",            # save workflow instead of running
        "{TMP}/deepl-later.toml",
        "n",            # don't open folder containing the saved workflow
    ],
    expect_state={"mt_engine": "deepl"},
    expect_stdout_contains=[
        "DeepL API key",
        # _wizard_run_setup prints the suggested fix once setup begins.
        "getsubtitle --set-key deepl",
        "Dependency check — issues found:",
        "Not running yet, because this workflow would fail before it starts.",
    ],
    # We declined the per-gap --set-key invocation, so set_api_keys
    # must NOT have been called; if it were, the wizard would have
    # printed "✓ key saved" (per _wizard_run_setup).
    expect_stdout_lacks=["✓ key saved"],
    expect_main_call_count=0,
)
