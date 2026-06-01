"""Trap: typing a title at the Q1 source-kind choice prompt must be
rejected (it's a numbered pick, not a free-text input) and the user
must stay on Q1.

Regression: an earlier version silently accepted any input at Q1's
source-kind prompt, which produced confusing downstream behavior
because `state.source_kind` was inferred from the typed string in
ways the user didn't intend.

After the wrong input, the user picks '3' (folder) and a real local
path so the wizard can complete and we can assert the steady state."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_q1_rejects_free_text",
    files={
        "{TMP}/Foo/Foo.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Foo/Foo.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    # 1) Q1 steps: default fetch+modify+merge (Enter).
    # 2) source: free-text "totoro" → must reprompt.
    # 3) source retry: "3" (folder/file).
    # 4) path: the staged folder.
    # 5) languages: ja,en.
    # 6) reading aids: 1 (skip).
    # 7) action: 5 (quit).
    inputs=[
        "",       # Q1 steps default
        "totoro", # invalid source pick
        "3",      # correct source pick (folder/file)
        "{TMP}/Foo",  # path
        "ja,en",  # languages
        "1",      # reading aids — skip
        "5",      # quit at action menu
    ],
    expect_stdout_contains=[
        "Invalid selection. Type 1, 2, or 3.",
    ],
    expect_state={
        "source_kind": "path",
        "languages": ["ja", "en"],
    },
)
