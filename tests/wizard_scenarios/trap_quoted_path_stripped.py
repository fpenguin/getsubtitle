"""Trap: drag-drop into the terminal often wraps the path in single
or double quotes (Finder, GNOME Files, KDE Dolphin). The wizard must
strip matching wrappers before validating, or the workflow stalls on
"path not found: '..."."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_quoted_path_stripped",
    files={
        "{TMP}/Foo Bar/Foo Bar.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Foo Bar/Foo Bar.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",                  # modify + merge (no a/b/c branch)
        "'{TMP}/Foo Bar'",      # quoted folder path (Finder drag-drop shape)
        "ja,en",                # languages
        "1",                    # reading aids — skip
        "5",                    # quit
    ],
    expect_state={"steps": {"modify", "merge"}},
    # The stored source must be the unquoted folder path.
    expect_stdout_lacks=["path not found"],
)
