"""Trap: adding Merge from the language prompt must expose format editing.

The user may start with Fetch only, then accept the wizard's recommended
Modify + Merge steps after choosing multiple languages. The flow must ask
for an output format, and the edit review loop must still show the
format/extension row.
"""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_edit_added_merge_can_change_format",
    files={
        "{TMP}/Show/Show.S01E01.ko.srt": "1\n00:00:01,000 --> 00:00:02,000\n안녕\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "1",            # fetch only
        "3",            # source = folder/file on disk
        "{TMP}/Show",
        "ko.en",        # typo-like separator
        "y",            # accept ko,en clarification
        "y",            # add recommended Modify + Merge so format/extension exists
        "1",            # no reading aids
        "",             # format — accept recommended SRT first
        "",             # font size — regular
        "2",            # action: change something
        "8",            # format / extension
        "2",            # ASS
        "",             # font size — regular for ASS
        "done",         # leave edit review
        "q",            # quit; no run/save needed
    ],
    expect_state={
        "steps": {"fetch", "modify", "merge"},
        "languages": ["ko", "en"],
        "format": "ass",
    },
    expect_stdout_contains=[
        "Did you mean ko,en?",
        "Selected: fetch + modify + merge.",
        "Final output format.",
        "2) ASS  — best for local study playback",
        "8) format / extension: SRT",
        "format / extension: ASS",
    ],
)
