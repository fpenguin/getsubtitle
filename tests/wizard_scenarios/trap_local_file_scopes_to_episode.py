"""Trap: when the user enters a specific video filename, downstream
modify/merge must operate on that one episode/file only, not on the
whole parent season folder.

The wizard infers `--season N --episode M` from the filename and
swaps `state.source` to the parent folder so sidecar subtitles still
get picked up — but the episode filter narrows the work scope down."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_local_file_scopes_to_episode",
    files={
        # Match an existing release-style filename so parse_episode_marker
        # picks up SxxExx cleanly.
        "{TMP}/Show/Show.S02E05.1080p.WEB-DL.mp4": "",
        "{TMP}/Show/Show.S02E05.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nひ\n",
        "{TMP}/Show/Show.S02E05.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nhi\n",
    },
    inputs=[
        "3,4",                                  # steps: modify + merge
        "{TMP}/Show/Show.S02E05.1080p.WEB-DL.mp4",  # specific video file
        "ja,en",                                # languages
        "1",                                    # reading aids — skip
        "",                                     # final format → recommended SRT
        "",                                     # font size → Regular
        "5",                                    # quit
    ],
    expect_state={
        "steps": {"modify", "merge"},
        "season": "2",
        "episode": "5",
        "languages": ["ja", "en"],
    },
    expect_stdout_contains=[
        "Selected episode: S02E05",
    ],
    # CLI must carry the episode filter on both verbs.
    expect_cli_contains=["--season", "--episode"],
)
