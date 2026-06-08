"""Persona: drag-and-drop user.

User drags a folder from Finder into the Terminal. macOS Terminal
wraps the dropped path in single quotes when the path contains
spaces; GNOME Files / KDE Dolphin do the same.

The wizard's `_wizard_describe_path_source` strips matched wrapping
quotes before validation."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_drag_quoted",
    files={
        "{TMP}/Shows/Foo Bar/Foo Bar.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Shows/Foo Bar/Foo Bar.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",                          # modify + merge
        "'{TMP}/Shows/Foo Bar'",        # single-quoted path
        "ja,en",
        "1",                            # reading aids — skip
        "",                             # format — accept recommended SRT
        "",                             # font size — regular
        "4",                            # save
        "{TMP}/drag.toml",
        "n",
    ],
    expect_state={"steps": {"modify", "merge"}},
    # The TOML carries the path via [output].target for local-only
    # workflows. Confirm Foo Bar landed there and the wrapping single
    # quotes did NOT survive — `"'` would mean a stray quote leaked
    # into the quoted string value.
    expect_toml_contains=["Foo Bar", "[output]"],
    expect_toml_lacks=["\"'", "'\""],
    expect_stdout_lacks=["path not found"],
)
