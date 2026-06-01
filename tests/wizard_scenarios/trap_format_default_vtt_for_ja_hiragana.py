"""Trap: requesting `ja,en` with a hiragana reading aid should auto
pick `--format vtt`. Hiragana ruby renders cleanly only in VTT — SRT
falls back to parenthetical 漢字（かんじ） form, which is fine but
not what the user usually wants when they explicitly asked for a
reading aid.

The matching no-reading-aid scenario lives in
`persona_furigana_newbie` (which picks hiragana too — the contrast
case is `persona_re_runner` which keeps reading aids off and ends up
with `--format srt`)."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_format_default_vtt_for_ja_hiragana",
    files={
        "{TMP}/Show/Show.S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",          # modify + merge
        "{TMP}/Show",
        "ja,en",
        "2",            # reading aids: pick #2 = ja:hiragana
        "2",            # action: save
        "{TMP}/vtt-ja.toml",
        "n",            # decline open folder
    ],
    expect_state={
        "reading_aids": ["ja:hiragana"],
        "format": "vtt",
    },
    expect_cli_contains=["--format", "vtt"],
    expect_toml_contains=['format = "vtt"', 'reading = "ja:hiragana"'],
)
