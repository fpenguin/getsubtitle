"""Persona: user mistypes 'restart' at the action menu, then backs
out.

Restart wipes 10+ answers, so the wizard asks 'Discard all answers
and start over?' before clearing state. If the user says no, the
wizard returns to the action menu with state intact — they do NOT
re-enter the wizard from scratch."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_restart_decline",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",
        "{TMP}/Show",
        "ja,en",
        "1",            # reading aids — skip
        "",             # final format → recommended SRT
        "",             # font size → Regular
        "4",            # action: restart
        "n",            # confirm: 'Discard all answers and start over?' → no
        "5",            # back at action menu: quit
    ],
    expect_state={
        # Confirms state survived the restart-cancel: languages still set.
        "languages": ["ja", "en"],
        "steps": {"modify", "merge"},
    },
    expect_stdout_contains=["Discard all answers and start over?"],
)
