"""Persona: natural title at Q2.

User typing the show title at the source-kind prompt is a common
first-run move. The wizard should infer "title search" and continue
instead of making the user back up and choose the title option first."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_title_typo_at_q1",
    files={},
    inputs=[
        "",         # steps default (1-4)
        "totoro",   # source-kind prompt accepts free text as title search
        "2",        # advanced raw-title escape after no resolver hit
        "n",        # "Is this a movie?" → no
        "2",        # scope: specific season + episode
        "1",        # season
        "1",        # episode
        "ja,en",    # languages
        "1",        # missing-language action — skip
        "1",        # reading aids — skip
        "",         # format — accept recommended SRT
        "",         # font size — regular
        "4",        # save action
        "{TMP}/totoro-typo.toml",
        "n",        # decline open folder
    ],
    expect_state={
        "source": "totoro",
        "source_kind": "title",
    },
    expect_stdout_contains=[
        "Detected title search:",
        "Searching for: 'totoro'",
    ],
)
