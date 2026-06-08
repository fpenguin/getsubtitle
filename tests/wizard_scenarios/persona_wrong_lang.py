"""Persona: user has a Korean-only subtitle but asks for ja+en, then
declines the offer to search online.

The wizard prints the local language inventory + missing-list, asks
'search online?', and on 'no' prints the restart hint instead of
silently continuing to a doomed modify/merge.

This is the negative-path twin of persona_plex_mash."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_wrong_lang",
    files={
        "{TMP}/Foo/Foo.S01E01.ko.srt": "1\n00:00:01,000 --> 00:00:02,000\n안녕\n",
    },
    inputs=[
        "3,4",          # modify + merge
        "{TMP}/Foo",    # folder
        "ja,en",
        "n",            # decline fetch on missing langs → see restart hint
        "1",            # reading aids — skip
        "",             # format — accept recommended SRT
        "",             # font size — regular
        "q",            # quit
    ],
    expect_state={
        "steps": {"modify", "merge"},
        "source_kind": "path",
    },
    expect_stdout_contains=[
        "Found locally: ko",
        "Missing for your requested stack: ja, en",
        "restart with `getsubtitle -i`, choose Fetch",
    ],
)
