"""Persona: typo-at-Q1 recovery.

User typing the show title at the Q1 source-kind prompt is a common
mis-step. The wizard must reject the free-text answer and keep the
user on Q1 (with an explanatory hint), then accept the correct
numeric pick on the retry.

This is the same trap as `trap_q1_rejects_free_text` but the recovery
path follows through to the title prompt + raw-text fallback."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_title_typo_at_q1",
    files={},
    inputs=[
        "",         # steps default (1-4)
        "totoro",   # wrong: free text at Q1
        "1",        # correct: title search
        "Totoro",   # title to search
        "n",        # "Is this a movie?" → no
        "2",        # scope: specific season + episode
        "1",        # season
        "1",        # episode
        "ja,en",    # languages
        "1",        # missing-language action — skip
        "1",        # reading aids — skip
        "",         # final format → recommended SRT
        "",         # font size → Regular
        "2",        # save action
        "{TMP}/totoro-typo.toml",
        "n",        # decline open folder
    ],
    expect_state={
        "source": "Totoro",
        "source_kind": "title",
    },
    expect_stdout_contains=[
        "Invalid selection. Type 1, 2, or 3.",
        "title search for 'Totoro'",
    ],
)
