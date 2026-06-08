"""Trap: partial local subtitle coverage should be explained before Run.

Folder has S01E01 ja+en but S01E02 only ja. The wizard should call out
the missing language before dispatching modify/merge.
"""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_partial_local_coverage_preflight",
    files={
        "{TMP}/Show/Show - S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n",
        "{TMP}/Show/Show - S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        "{TMP}/Show/Show - S01E02.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nまたね\n",
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
        "Coverage estimate: 1/2 episode(s) already have all requested languages",
        "S01E02 missing en",
    ],
    expect_main_call_count=1,
)
