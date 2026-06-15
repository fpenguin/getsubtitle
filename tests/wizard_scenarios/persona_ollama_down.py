"""Persona: user picks Ollama but the local daemon is not running.

The dependency probe must call out 'Ollama daemon at
http://localhost:11434' with severity `block`, hint at the install
URL, and avoid dispatching a doomed run while the daemon is still down.
The transcript must name Ollama specifically, not produce a generic
"engine missing" line."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_ollama_down",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "2,3,4",        # translate + modify + merge
        "{TMP}/Show",
        "ja,en",
        "5",            # translate engine: Qwen3 via Ollama
        "1",            # reading aids — skip
        "",             # format — accept recommended SRT
        "",             # font size — regular
        "1",            # action: run
        "y",            # show setup steps
        # _wizard_run_setup prints a "Manual step" hint for the Ollama
        # gap and does NOT ask a per-gap yes/no (it only prompts for
        # set-key-shaped fixes), so no extra input is consumed here.
        "y",            # save workflow instead of running
        "{TMP}/ollama-later.toml",
        "n",            # don't open folder containing the saved workflow
    ],
    expect_state={"mt_engine": "ollama"},
    expect_stdout_contains=[
        "Ollama daemon at http://localhost:11434",
        # The setup walker re-prints the suggested fix verbatim.
        "Start Ollama: https://ollama.com",
        "(Manual step — re-launch the wizard once done.)",
        "Still blocked — the run would fail before it starts:",
    ],
    expect_main_call_count=0,
)
