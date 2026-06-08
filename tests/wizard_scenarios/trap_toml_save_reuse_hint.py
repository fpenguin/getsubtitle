"""Trap: after the user saves a workflow TOML, the wizard must keep the
success path short while making details available on demand. Choosing
"Show exact command" should reveal the `--config FILE.toml` reuse hint
and how CLI overrides layer on top (e.g. `--source URL --output PATH`)."""

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
        "",             # format — accept recommended SRT
        "",             # font size — regular
        "2",            # action: save
        "{TMP}/Reusable.toml",  # save filename
        "1",            # show exact command/details
        "2",            # open containing folder
        "3",            # done
    ],
    expect_state={"steps": {"modify", "merge"}},
    expect_stdout_contains=[
        "getsubtitle --config",
        "--source",
        "--output",
        "Open containing folder",
        "CLI flags win over matching TOML settings",
    ],
    # 'save' must not dispatch main().
    expect_main_call_count=0,
)
