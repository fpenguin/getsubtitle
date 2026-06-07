"""Persona: merge-only on a folder of .srt files.

The wizard must skip the translate-engine, reading-aid, and master/
format questions because none of them apply to a pure merge. The
banner shows the equivalent `getsubtitle merge PATH ...` command."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_merge_only_folder",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "4",            # merge only
        "{TMP}/Show",
        "ja,en",
        "n",            # decline 'Add Modify step for reading aids?'
        "",             # final format → recommended SRT
        "",             # font size → Regular
        "2",            # save
        "{TMP}/merge-only.toml",
        "n",
    ],
    expect_state={"steps": {"merge"}},
    expect_cli_contains=["getsubtitle", "merge"],
    expect_cli_lacks=["--modify", "--fetch", "--translate"],
    # The skipped Q prompts must not show up in the transcript.
    expect_stdout_lacks=[
        "If a language is missing",   # Q6 translate prompt
        "Reading aids (phonetic guides",  # Q7 reading prompt
    ],
)
