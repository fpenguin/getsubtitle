"""Trap: saying yes to the post-run 'Open folder?' prompt must open
Finder/Explorer for the output directory ONLY. It must not kick off
a second modify/merge pass over ~/Downloads/GetSubtitle or any other
default folder.

This regressed once when the open-folder hook was reusing the
`run_state`'s pipeline argv to determine the target — and the pipeline
argv would then accidentally be re-dispatched."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_open_folder_only_opens",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",          # steps: modify + merge
        "{TMP}/Show",   # path
        "ja,en",
        "1",            # reading aids — skip
        "",             # format — accept recommended SRT
        "",             # font size — regular
        "1",            # action: run
        "y",            # open folder? yes
    ],
    expect_state={"steps": {"modify", "merge"}},
    # `--no-open-folder-prompt` is injected by the wizard so the inner
    # merge_main doesn't double-prompt. It must NOT leak into the
    # transcript as a user-visible flag mention either.
    expect_stdout_contains=["Open folder?"],
    expect_cli_lacks=["--no-open-folder-prompt"],
    # Exactly ONE main() dispatch — saying yes to 'Open folder?' must
    # not re-run the pipeline.
    expect_main_call_count=1,
)
