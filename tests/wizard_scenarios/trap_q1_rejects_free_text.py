"""Trap: typing a title at the source-kind prompt is accepted.

Regression target changed: natural text input should now be treated
as a title search, not rejected as an invalid menu number."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_q1_rejects_free_text",
    files={
        "{TMP}/Foo/Foo.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Foo/Foo.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    # 1) Q1 steps: default 1-4 (Enter).
    # 2) source: free-text "totoro" → title search.
    # 3) raw-title movie? no.
    # 4) scope: auto.
    # 5) languages: ja,en.
    # 6) missing-language action: 1 (skip AI translation).
    # 7) reading aids: 1 (skip).
    # 8) format/font/action defaults as scripted.
    inputs=[
        "",       # Q1 steps default
        "totoro", # title search
        "n",      # raw title is TV/show
        "",       # scope auto
        "ja,en",  # languages
        "1",      # missing-language action — skip
        "1",      # reading aids — skip
        "",       # format — accept recommended SRT
        "",       # font size — regular
        "5",      # quit at action menu
    ],
    expect_stdout_contains=[
        "Detected title search:",
        "Searching for: 'totoro'",
    ],
    expect_state={
        "source_kind": "title",
        "source": "totoro",
        "languages": ["ja", "en"],
    },
)
