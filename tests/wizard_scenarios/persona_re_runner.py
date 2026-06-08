"""Persona: experienced user wants a reusable workflow file.

User completes the wizard with a URL source, picks `save`, and types a
save path. The post-save success path should stay short: show the saved
file, the `--config` command, and the optional details menu."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_re_runner",
    files={},
    inputs=[
        "1,3,4",        # fetch + modify + merge
        "2",            # URL
        "https://www.imdb.com/title/tt28299608/",
        "2",            # scope: specific season + episode
        "1",
        "1",
        "ja,en",
        "1",            # reading aids — skip
        "",             # format — accept recommended SRT
        "",             # font size — regular
        "2",            # action: save (URL default)
        "{TMP}/saved.toml",
        "n",            # decline open folder
    ],
    expect_state={"steps": {"fetch", "modify", "merge"}},
    expect_stdout_contains=[
        "Saved workflow:",
        "getsubtitle --config",
        "Run later:",
        "Show exact command",
    ],
    expect_main_call_count=0,
)
