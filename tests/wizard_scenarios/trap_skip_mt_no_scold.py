"""Trap: choosing 'Skip — accept the gap' at the MT engine question
must NOT print a warning chastising the user for disabled MT.
Missing-language output is informational coverage data, not a scold.

The CLI must carry `--no-engine` so the downstream fetch flow stays
in 'don't try to translate' mode."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_skip_mt_no_scold",
    files={},  # URL flow — no local files needed
    inputs=[
        "1,2,3,4",      # steps: all four (so translate Q fires)
        "2",            # Q1 source: URL
        "https://www.imdb.com/title/tt28299608/",  # URL
        "3",            # Q4 scope: auto
        "ja,en",        # languages
        "1",            # Q6 translate: Skip — accept gap
        "1",            # Q7 reading aids: skip
        "",             # format — accept recommended SRT
        "",             # font size — regular
        "4",            # Q12 action: save (default for URL)
        "{TMP}/saved.toml",   # save filename (absolute to avoid cwd pollution)
        "n",            # open folder containing saved file → no
    ],
    expect_state={
        "mt_engine": "",
        "languages": ["ja", "en"],
    },
    expect_cli_contains=["--no-engine"],
    expect_stdout_lacks=[
        # No scolding language about disabled MT.
        "disabled MT",
        "AI translation is disabled",
        "you turned off translation",
    ],
)
