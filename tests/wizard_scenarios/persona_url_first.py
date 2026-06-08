"""Persona: URL-first user.

User pastes an IMDb URL, picks fetch + modify + merge, asks for ja+en
plus a hiragana reading aid. Smart defaults pick `--format vtt` and
`~/Downloads/GetSubtitle` for the output folder.

The action menu defaults to `save` for URL/title sources (so muscle-
memory Enter doesn't kick off a long network job). The scenario
follows that default-pick path."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_url_first",
    files={},
    inputs=[
        "1,3,4",        # fetch + modify + merge
        "2",            # URL source
        "https://www.imdb.com/title/tt28299608/",
        "2",            # Q5 scope: specific season + episode
        "1",            # season 1
        "1",            # episode 1
        "ja,en",
        "2",            # reading aids: pick #2 = ja:hiragana
        "",             # format — accept recommended VTT
        "",             # action menu default — URL → 'b' (save)
        "{TMP}/url-first.toml",
        "n",            # decline open folder
    ],
    expect_state={
        "steps": {"fetch", "modify", "merge"},
        "source_kind": "url",
        "reading_aids": ["ja:hiragana"],
        "format": "vtt",
        "output": "~/Downloads/GetSubtitle",
    },
    expect_cli_contains=[
        "--fetch", "https://www.imdb.com/title/tt28299608/",
        "--reading", "ja:hiragana",
        "--format", "vtt",
    ],
    expect_toml_contains=[
        '[fetch]',
        'reading = "ja:hiragana"',
        'format = "vtt"',
    ],
)
