"""Trap: every [Y/n] / a/b/c prompt with a default must accept Enter.

This regressed once in the asbplayer/cleanup branch where an empty
answer fell through to the 'please enter something' loop instead of
honoring the default. The scenario presses Enter at every prompt that
has a default, providing only the bare-minimum required answers
(path, languages can also default to ja,en).

Defaults exercised:
- Q1 steps: 1-4 (fetch+translate+modify+merge)
- Q1 source choice: 'c' when no TMDB key configured
- Q4 languages: ja,en
- missing-language action: skip AI translation
- Q7 reading aids: 1 (skip)
- Q12 action: 'a' (run) for local path source

The 'run' branch then dispatches `main()` (stubbed by the harness),
hits the post-run open-folder prompt (default Y), and exits 0."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_enter_accepts_default",
    files={
        "{TMP}/Foo/Foo.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Foo/Foo.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "",            # Q1 steps default
        "",            # Q1 source choice (Enter → '3' folder when no TMDB key)
        "{TMP}/Foo",    # path — only required answer
        "",            # Q4 languages → 'ja,en'
        "",            # missing-language action → skip AI translation
        "",            # Q7 reading aids → '1' (skip)
        "",            # format → SRT
        "",            # font size → regular
        "",            # Q12 action — Enter accepts default '1' (run) for path source
        "",            # post-run open folder → default Y
    ],
    expect_state={
        "steps": {"fetch", "translate", "modify", "merge"},
        "languages": ["ja", "en"],
        "reading_aids": [],
    },
    expect_stdout_lacks=[
        "(empty answer; please enter something",
    ],
)
