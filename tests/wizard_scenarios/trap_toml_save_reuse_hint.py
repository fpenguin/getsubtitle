"""Trap: after the user saves a workflow TOML, the wizard must surface
the reuse hint that explains `--config FILE.toml` AND show how CLI
overrides layer on top (e.g. `--source URL --output PATH`). Then it
must offer to open the folder containing the file."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_toml_save_reuse_hint",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",          # modify + merge
        "{TMP}/Show",   # path
        "ja,en",
        "1",            # reading aids — skip
        "2",            # action: save
        "{TMP}/Reusable.toml",  # save filename
        "n",            # decline opening the save folder
    ],
    expect_state={"steps": {"modify", "merge"}},
    expect_stdout_contains=[
        "getsubtitle --config",
        "--source",
        "--output",
        "Open folder containing Reusable.toml?",
        "CLI flags win over matching TOML settings",
    ],
    # 'save' must not dispatch main().
    expect_main_call_count=0,
)
