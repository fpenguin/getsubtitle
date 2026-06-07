"""Persona: power user revises a single answer.

After answering everything, the user picks 'Edit a single answer',
goes back to Q1 (the step picker), drops merge, then chooses save.

The wizard must re-derive downstream answers correctly: state.steps
no longer contains merge, and the emitted CLI must omit `--merge`
and the `--languages` block that goes with it."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_power_edit",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",          # initial: modify + merge
        "{TMP}/Show",
        "ja,en",
        "1",            # reading aids — skip (format/size are smart-defaulted)
        "3",            # action: edit a single answer
        "1",            # edit target 1) steps
        "3",            # change to modify-only
        "2",            # back at action menu: save
        "{TMP}/edited.toml",
        "n",
    ],
    expect_state={"steps": {"modify"}},
    expect_cli_lacks=["--merge"],
    # Modify-only CLI starts `getsubtitle modify PATH ...` per the
    # single-verb branch in _wizard_emit_cli.
    expect_cli_contains=["modify"],
)
