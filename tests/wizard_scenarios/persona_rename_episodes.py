"""Persona: tidy up subtitle filenames with rename mode.

Exercises the v0.9.6 rename fixes end-to-end:
- B3: an unparseable file in the folder is reported as skipped, not
  silently ignored.
- B1: renumbering an episode range keeps the ja/en variants of the same
  episode paired (both E01 -> E05), proven by the previewed plan.
- Copy-and-apply is the safe default, so originals stay in place.
"""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="persona_rename_episodes",
    files={
        "{TMP}/Show/MF Ghost - S01E01.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\na\n",
        "{TMP}/Show/MF Ghost - S01E01.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nb\n",
        "{TMP}/Show/MF Ghost - S01E02.ja.srt": "1\n00:00:01,000 --> 00:00:02,000\nc\n",
        "{TMP}/Show/MF Ghost - S01E02.en.srt": "1\n00:00:01,000 --> 00:00:02,000\nd\n",
        # Unparseable (no " - " separator) — must be reported as skipped.
        "{TMP}/Show/MF Ghost S01E03 ja.srt": "1\n00:00:01,000 --> 00:00:02,000\ne\n",
    },
    inputs=[
        "5",            # Q1: rename only
        "{TMP}/Show",   # source folder
        "all",          # work on all variations (ja + en)
        "3",            # change Episode
        "2",            # change range
        "5",            # first episode number in new range
        "1",            # Looks good — apply now
        "1",            # Copy and apply (keep originals)
        "y",            # confirm
    ],
    expect_state={"steps": {"rename"}},
    expect_stdout_contains=[
        # B3: skip report for the unparseable file.
        "Skipping 1 file(s) that don't match",
        "MF Ghost S01E03 ja.srt",
        # B1: ja and en of E01 both renumber to E05 (paired).
        "-> MF Ghost - S01E05.ja.srt",
        "-> MF Ghost - S01E05.en.srt",
        "Copied 4 renamed file(s).",
    ],
)
