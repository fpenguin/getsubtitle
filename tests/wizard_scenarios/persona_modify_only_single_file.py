"""Persona: user has a single .ja.srt and wants to add a reading aid.

Modify-only flow. The wizard must emit `getsubtitle modify PATH ...`
(subcommand form, not pipeline `--source PATH --modify`)."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_modify_only_single_file",
    files={
        "{TMP}/Foo.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
    },
    inputs=[
        "3",            # modify only
        "{TMP}/Foo.ja.srt",  # single .srt file
        "ja",           # languages
        "2",            # reading aids: pick #2 = ja:hiragana
        "2",            # save
        "{TMP}/single-file.toml",
        "n",            # decline open folder
    ],
    expect_state={"steps": {"modify"}},
    expect_cli_contains=["getsubtitle", "modify"],
    # No pipeline-form flags.
    expect_cli_lacks=[
        "--no-open-folder-prompt", "--source", "--fetch", "--merge",
    ],
)
