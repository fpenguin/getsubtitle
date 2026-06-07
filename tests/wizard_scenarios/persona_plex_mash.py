"""Persona: Mashle on Plex.

User drops a single .mkv (their downloaded episode) + a Korean .smi
sidecar, picks modify + merge, asks for ja+en. The wizard:

  1. Infers s02e13 from the filename.
  2. Detects the .smi sidecar and auto-adds `--convert smi-to-srt`.
  3. Notices that only `ko` is locally available, NOT `ja`/`en`.
  4. Offers to add Fetch on the spot, with a title input.

User says yes and types "Mashle". The wizard re-routes the source
to title-search, preserves the original folder as the output, and
adds `fetch` to state.steps.

This is the canonical 'beginner is starting from local files and
realises mid-flow they need to download' scenario."""

from wizard_harness import Scenario

_SAMI_KO = """\
<SAMI>
<HEAD><STYLE TYPE="text/css"><!--
.KRCC {Name: Korean; lang: ko-KR; SAMI_Type: CC;}
--></STYLE></HEAD>
<BODY>
<SYNC Start=1000><P Class=KRCC>안녕하세요</P></SYNC>
<SYNC Start=3500><P Class=KRCC>&nbsp;</P></SYNC>
</BODY>
</SAMI>
"""

SCENARIO = Scenario(
    name="persona_plex_mash",
    files={
        "{TMP}/Mashle/Mashle - s02e13.mkv": "",
        "{TMP}/Mashle/Mashle - s02e13.smi": _SAMI_KO,
    },
    inputs=[
        "3,4",                                  # steps: modify + merge
        "{TMP}/Mashle/Mashle - s02e13.mkv",     # the specific video
        "ja,en",                                # ask for Japanese + English
        "y",                                    # accept fetch on missing langs
        "Mashle",                               # title to search for (preflight branch)
        # Scope was already pinned to S02E13 from the filename, so the
        # scope question shows "already selected" and does NOT prompt
        # (CODEX bug-fix #1). No season/episode re-entry here.
        "1",                                    # reading aids — skip
        "",                                     # final format → recommended SRT
        "",                                     # font size → Regular
        "2",                                    # save (URL/title default)
        "{TMP}/mashle.toml",                    # save filename
        "n",                                    # decline open folder
    ],
    expect_state={
        "steps": {"fetch", "modify", "merge"},
        "convert_smi": True,
        "season": "2",
        "episode": "13",
        "source_kind": "title",
    },
    expect_cli_contains=[
        "--convert", "smi-to-srt",
        "--fetch", "--title",
    ],
    expect_stdout_contains=[
        "Selected episode: S02E13",
        "SMI subtitles found",
        "Found locally: ko",
        "Missing for your requested stack: ja, en",
    ],
)
