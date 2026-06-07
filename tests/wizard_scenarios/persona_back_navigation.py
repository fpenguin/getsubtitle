"""Persona: user goes back one step during the wizard.

The user starts a local modify+merge workflow, enters one folder, then
realises they picked the wrong source while answering languages. Typing
`b` should return to the previous visible step, clear that answer,
and let the new source flow through to the emitted command/TOML.
"""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_back_navigation",
    files={
        "{TMP}/Wrong/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\n違う\n",
        "{TMP}/Right/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\n正しい\n",
        "{TMP}/Right/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\ncorrect\n",
    },
    inputs=[
        "3,4",          # modify + merge
        "{TMP}/Wrong",
        "b",            # from language prompt, go back to source
        "{TMP}/Right",
        "ja,en",
        "1",            # reading aids — skip
        "2",            # save workflow
        "{TMP}/back.toml",
        "n",            # do not open folder
    ],
    expect_cli_contains=["Right"],
    expect_cli_lacks=["Wrong"],
    expect_toml_contains=["Right"],
    expect_toml_lacks=["Wrong"],
    expect_stdout_contains=["Going back to the previous step."],
)
