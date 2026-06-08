"""Trap: existing merged outputs should be visible before Run.

The merge command already skips existing output files unless --force is
used. The wizard should warn in preflight too, so a beginner does not
wait for the run only to learn nothing was written.
"""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_existing_merge_output_preflight",
    files={
        "{TMP}/Show/Show - S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n",
        "{TMP}/Show/Show - S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        "{TMP}/Show/Show - S01E01.ja-en.srt": "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\nHello\n",
    },
    inputs=[
        "3,4",        # modify + merge
        "{TMP}/Show",
        "ja,en",
        "1",          # no reading aid
        "",           # format — accept recommended SRT
        "",           # font size — regular
        "1",          # run
        "n",          # don't open folder
    ],
    expect_stdout_contains=[
        "Existing output files detected for 1/1 selected episode(s)",
        "Show - S01E01.ja-en.srt",
        "Choose a different output folder",
    ],
    expect_main_call_count=1,
)
