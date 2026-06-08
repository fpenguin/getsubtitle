"""Persona: a folder of movie subtitles (no SxxExx in filenames).

A learner downloaded `Totoro.ja.srt` and `Totoro.en.srt` (movie-style
filenames produced by save_subtitle). They open the wizard, pick
merge-only, and point it at the folder.

This is the v0.7.1 movie re-scannability test — `parse_episode_marker`
must return synthetic (0, 0) so the scanner sees both files."""

from wizard_harness import Scenario

_SRT_JA = "1\n00:00:01,000 --> 00:00:02,000\n日本語\n"
_SRT_EN = "1\n00:00:01,000 --> 00:00:02,000\nHello\n"

SCENARIO = Scenario(
    name="persona_folder_movie",
    files={
        "{TMP}/Totoro/Totoro.ja.srt": _SRT_JA,
        "{TMP}/Totoro/Totoro.en.srt": _SRT_EN,
    },
    inputs=[
        "4",            # merge only
        "{TMP}/Totoro", # folder
        "ja,en",
        "n",            # decline 'Add Modify step for reading aids?'
        "",             # format — accept recommended SRT
        "",             # font size — regular
        "4",            # save action (deterministic vs path-default '1')
        "{TMP}/totoro.toml",
        "n",            # decline open folder
    ],
    expect_state={
        "steps": {"merge"},
        "languages": ["ja", "en"],
    },
    expect_cli_contains=[
        "getsubtitle", "merge",
    ],
    # Merge-only emitter is a single subcommand; no --modify / --fetch.
    expect_cli_lacks=["--modify", "--fetch", "--translate"],
)
