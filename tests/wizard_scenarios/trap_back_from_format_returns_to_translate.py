"""Trap: pressing back at the format question must return to the previous
visible question, not re-display the format question.

This regressed when format became an explicit wizard step before font size:
the history stack could contain "format", so `b` popped and re-asked the
current step instead of returning to the translate choice.
"""

from wizard_harness import Scenario


SCENARIO = Scenario(
    name="trap_back_from_format_returns_to_translate",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhello\n",
    },
    keys={"deepl": "fake-key-for-test"},
    inputs=[
        "2,4",          # translate + merge; no modify/reading-aids step
        "{TMP}/Show",
        "ja,en",
        "n",            # do not add Modify just because Japanese is present
        "1",            # translate: skip
        "b",            # at format: go back to translate
        "4",            # translate: DeepL
        "",             # final format → recommended SRT
        "",             # font size → Regular
        "2",            # save workflow (path source would default to run)
        "{TMP}/back-format.toml",
        "n",
    ],
    expect_state={
        "mt_engine": "deepl",
        "format": "srt",
    },
    expect_stdout_contains=[
        "Going back to the previous step.",
        "If a language is missing, what should we do?",
    ],
    expect_cli_contains=["--translate", "deepl"],
    expect_toml_contains=['engine = "deepl"', 'format = "srt"'],
)
