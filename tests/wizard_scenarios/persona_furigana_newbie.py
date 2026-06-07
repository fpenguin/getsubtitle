"""Persona: new Japanese learner sees the reading-aid menu for the
first time.

Before the menu of options, the prompt MUST describe what reading
aids are (so the newcomer doesn't blindly hit Enter on a feature
they wanted). The format-rendering note (VTT ruby vs parenthetical
in SRT/SMI/ASS) must also be present so the user understands why
the wizard later picks VTT."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_furigana_newbie",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",          # modify + merge
        "{TMP}/Show",
        "ja,en",
        "2",            # reading aids: pick #2 = ja:hiragana
        "",             # final format → recommended VTT (font size skipped)
        "2",            # save
        "{TMP}/newbie.toml",
        "n",            # decline open folder
    ],
    expect_state={
        "reading_aids": ["ja:hiragana"],
        "format": "vtt",
    },
    expect_stdout_contains=[
        # Description text precedes the menu.
        "Reading aids (phonetic guides for the original script)",
        "VTT renders them as ruby above the script",
        "1) No reading aid (skip)",
        "Japanese — hiragana readings for kanji",
    ],
)
