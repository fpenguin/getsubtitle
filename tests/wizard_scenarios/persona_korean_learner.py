"""Persona: Korean learner (ko,en) wants Revised Romanization.

This scenario closes the coverage gap that earlier made the Q7
reading-aid menu *look* Japanese-only: every other scenario happens to
request `ja`, so the blessed transcripts only ever showed the three
Japanese rows. The Q7 menu actually filters
`_WIZARD_READING_AID_MENU` by the requested languages
(`row[0] in state.languages`), so a `ko,en` request must surface the
Korean rows — and must NOT show the Japanese ones.

Folder already has both requested languages (ko + en) locally, so the
missing-language preflight stays quiet and no Fetch is offered."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_korean_learner",
    files={
        "{TMP}/Show/Show.S01E01.ko.srt": "1\n00:00:01,000 --> 00:00:02,000\n안녕\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",            # modify + merge (local files, no fetch)
        "{TMP}/Show",
        "ko,en",
        "2",              # reading aids: #2 = ko:revised (menu filtered to Korean)
        "",               # final format → recommended ASS
        "",               # font size → Regular
        "2",              # save
        "{TMP}/korean.toml",
        "n",              # decline open folder
    ],
    expect_state={
        "reading_aids": ["ko:revised"],
        "format": "ass",
        "languages": ["ko", "en"],
        "steps": {"modify", "merge"},
    },
    expect_stdout_contains=[
        "Reading aids (phonetic guides for the original script)",
        "1) No reading aid (skip)",
        # The Korean rows must appear for a ko,en request.
        "Korean — Revised Romanization",
        "Korean — Yale Romanization",
    ],
    expect_stdout_lacks=[
        # Proof the menu filtered by language — no Japanese rows leak in.
        "Japanese — hiragana readings for kanji",
        "Japanese — full-sentence romaji",
    ],
    expect_toml_contains=[
        'reading = "ko:revised"',
    ],
)
