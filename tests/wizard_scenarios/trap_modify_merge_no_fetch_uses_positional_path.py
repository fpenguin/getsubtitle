"""Trap: modify+merge without fetch must produce a valid CLI.

Earlier versions emitted `getsubtitle PATH --merge --languages ...`
which parses as a bare positional URL/path before any verb and gets
rejected. The fix carries the path via `--source PATH` in pipeline
form, so the CLI runs through the pipeline parser cleanly.

The scenario also covers the matching modify-only single-file case
(handled separately in persona_modify_only_single_file) and the
merge-only folder case (persona_merge_only_folder). Here we pin the
two-verb (modify+merge) flow specifically."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_modify_merge_no_fetch_uses_positional_path",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",        # Q1 steps: modify + merge (no fetch)
        "{TMP}/Show",  # Q2 path (single branch — no a/b/c when fetch absent)
        "ja,en",      # Q4 languages
        "1",          # Q7 reading aids — skip
        "",           # format — accept recommended SRT
        "",           # font size — regular
        "q",          # Q12 — quit
    ],
    expect_state={"steps": {"modify", "merge"}},
    # `--source PATH` carries the folder; the first positional in argv
    # is the verb namespace (`getsubtitle`), NOT a bare path.
    expect_cli_contains=["--source", "--modify", "--merge"],
    # No bare path positional before --modify.
    expect_cli_lacks=["--fetch"],
)
