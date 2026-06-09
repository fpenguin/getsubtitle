"""Trap: a local workflow with no subtitle files should warn before Run.

This is the "nothing to merge" beginner failure path. The wizard should
explain the folder problem before dispatching the command.
"""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_no_local_subtitles_preflight",
    files={
        "{TMP}/Show/Show - S01E01.mkv": "",
    },
    inputs=[
        "4",           # merge only
        "{TMP}/Show",
        "ja,en",
        "n",           # do not add Modify just for reading aids
        "",            # format — accept recommended SRT
        "",            # font size — regular
        "1",           # run
        "n",           # don't open folder
    ],
    expect_stdout_contains=[
        "No local subtitle files found",
        "Check the folder path, extract MKV subtitles, or fetch/download subtitles first.",
    ],
    expect_main_call_count=1,
)
