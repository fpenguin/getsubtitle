"""Trap: Crunchyroll series/watch URLs must not silently become S01E01.

Crunchyroll may display Season 3 as E25-E37, while subtitle sources
usually search that as Season 3 episodes 1-13. The wizard should ask
for season and episode-within-season before language choices, then emit
the explicit scope the user typed.
"""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_crunchyroll_auto_scope_requires_range",
    inputs=[
        "1,3,4",        # fetch + modify + merge
        "2",            # URL source
        "https://www.crunchyroll.com/watch/GZ7UDVKPD/miraculous-comeback",
        "1",            # specific season + episode/range
        "3",            # Season 3
        "1-13",         # Subtitle-source numbering for Season 3
        "2",            # output filenames should match page numbering
        "25",           # first episode shown on the page
        "ja,ko",
        "1",            # reading aids — skip
        "",             # format — accept recommended SRT
        "",             # font size — regular
        "2",            # save workflow
        "{TMP}/mfghost-s3.toml",
        "n",            # decline open folder
    ],
    expect_state={
        "season": "3",
        "episode": "1-13",
        "episode_filename_start": "25",
    },
    expect_cli_contains=[
        "--season", "3",
        "--episode", "1-13",
        "--episode-filename-start", "25",
    ],
    expect_cli_lacks=["--episode auto", "--episode 25-37", "S01E01"],
    expect_toml_contains=[
        'season = "3"',
        'episode = "1-13"',
        'episode_filename_start = "25"',
    ],
    expect_stdout_contains=[
        "Crunchyroll may display Season 3 as E25-E37",
        "Season or range",
        "Episode or range within each season",
        "How should episode numbers appear in output filenames?",
        "Output filenames will start at S03E25.",
    ],
)
