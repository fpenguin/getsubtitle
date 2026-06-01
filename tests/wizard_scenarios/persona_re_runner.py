"""Persona: experienced user wants a reusable workflow file.

User completes the wizard with a URL source (so save is the default
action), picks `save`, types a save path. The "Equivalent workflow
file (save as .toml):" banner must appear in the Q12 transcript,
and after saving the wizard prints the `--config` reuse hint."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_re_runner",
    files={},
    inputs=[
        "1,3,4",        # fetch + modify + merge
        "2",            # URL
        "https://www.imdb.com/title/tt28299608/",
        "ja,en",
        "2",            # scope: specific season + episode
        "1",
        "1",
        "1",            # reading aids — skip
        "2",            # action: save (URL default)
        "{TMP}/saved.toml",
        "n",            # decline open folder
    ],
    expect_state={"steps": {"fetch", "modify", "merge"}},
    expect_stdout_contains=[
        "Equivalent workflow file (save as .toml):",
        "getsubtitle --config",
        "Run it later with:",
        "You can recycle this TOML",
    ],
    expect_main_call_count=0,
)
