"""Persona: spam-Enter user.

Beginner instinctively hits Enter at every prompt expecting sensible
defaults. The wizard satisfies this as far as possible — every
prompt with a documented default treats empty input as the default
value. The only mandatory input is the source path (URL/path), since
neither has a defensible default.

The scenario provides one path and otherwise hits Enter. After the
smart-defaults pass, the final state must reflect the documented
defaults (ja,en languages, srt format with no reading aid, output
beside source for the path branch)."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_enter_spammer",
    files={
        "{TMP}/Foo/Foo.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Foo/Foo.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "",             # Q1 steps default → fetch+modify+merge
        "",             # Q1 source choice default → 'c' (no TMDB key)
        "{TMP}/Foo",    # path (mandatory — no default)
        "",             # languages → 'ja,en'
        "",             # reading aids → 1 (skip)
        "",             # action menu → 'a' (run) for path source
        "",             # open folder → Y
    ],
    expect_state={
        "steps": {"fetch", "modify", "merge"},
        "languages": ["ja", "en"],
        "reading_aids": [],
        "format": "srt",
    },
    expect_stdout_lacks=["(empty answer; please enter something"],
    expect_main_call_count=1,
)
