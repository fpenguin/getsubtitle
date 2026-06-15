# Representative wizard transcripts

These are harness-backed transcripts from `tests/wizard_transcripts/`.
Use them to audit copywriting, defaults, prompt ordering, and failure recovery.

## Tested paths

### path-01. Default full workflow, Enter-heavy happy path

- Category: `happy`
- Workflow: `fetch, translate, modify, merge`
- Scenario: `tests/wizard_scenarios/persona_enter_spammer.py`
- Audit focus: `defaults, progress, final_action`
- Notes: Shows whether defaults feel safe when the user keeps pressing Enter.

<details>
<summary>Show transcript (persona_enter_spammer)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] >
    Selected: fetch + translate + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Where should we get subtitles from?                             Progress [◼◼◻◻◻◻◻◻◻◻◻◻◻] 19%

    1) A movie/show title (The Simpsons, Totoro, The Matrix, …)
    2) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)
    3) A folder or file on disk (your Plex/Movies, ~/Downloads, …)

  Number [3 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q3. Enter the folder or file path.                                  Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 31%

  Folder or file path [b=back | q=quit] > {TMP}/Foo
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q4. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 44%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] >

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q5. Fill missing subtitles?                                         Progress [◼◼◼◼◼◼◼◻◻◻◻◻◻] 56%

    1) Skip
    2) DeepL                  online, polished, API key required
    3) Argos                  on-device, basic quality, cross-platform
    4) Apple Translation      on-device, Mac-only, system models required
    5) Qwen3                  on-device, general-purpose local AI
    6) TranslateGemma         on-device, translation-focused local AI

    Or type any Ollama model name, e.g. translategemma:12b or qwen3:14b.

  Number or model name [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 69%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q7. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 81%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q8. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 83%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Fetch Japanese, English for:
    {TMP}/Foo
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Foo

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] >

Preflight check — 1 item(s) to know about:
  • Local subtitles found for all requested languages
      Why: Heads-up — no action needed before running.
      Fix: Fast scan checked 2 subtitle candidate(s).

------------------------------------------------------------------------------------------------
Running:
  getsubtitle --fetch {TMP}/Foo --languages ja,en --modify --strip-cc-noise --single-line --merge --format srt --font-size regular --output {TMP}/Foo


======================================================================
Workflow summary
======================================================================
Completed successfully

Next steps:
  1. Merge later with: getsubtitle merge {TMP}/Foo -l ja,en
  2. Re-run this workflow command after any setup fixes:
     getsubtitle --fetch {TMP}/Foo --languages ja,en --modify --strip-cc-noise --single-line --merge --format srt --font-size regular --output {TMP}/Foo
  Open folder? [Y/n] >
```

</details>

### path-02. Local Plex folder with missing languages, then fetch

- Category: `common`
- Workflow: `fetch, modify, merge`
- Scenario: `tests/wizard_scenarios/persona_plex_mash.py`
- Audit focus: `missing_explanation, manual_search, source_reuse`
- Notes: Important for users who start from Plex folders instead of catalog URLs.

<details>
<summary>Show transcript (persona_plex_mash)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Mashle/Mashle - s02e13.mkv
    Selected episode: S02E13
    File selected; using its folder so matching subtitle files can be found.
    SMI subtitles found; will convert them to SRT before cleanup/readings.
    Searching for: local folder beside selected file: 0 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

    Local subtitle check:
      Found locally: ko
      Missing for your requested stack: ja, en
    If you continue without Fetch, modify/merge can only use the
    subtitle languages already in this folder.
  Search online for the missing languages now? [Y/n | b=back | q=quit] > y

    Enter an IMDb/TMDB/AniList/Crunchyroll URL, or type the title.

  URL or title to fetch [b=back | q=quit] > Mashle
    Fetch will save into: {TMP}/Mashle
    Then Modify/Merge will continue from that folder.

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◻◻◻◻◻] 64%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 69%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Fetch Japanese, English for:
    Mashle  (season 2, episode 13)
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Mashle

Before you run
  ⚠ Japanese subtitles can be harder to find automatically; manual
    search or translation may be needed.

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [4 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/mashle.toml

Saved workflow:
  {TMP}/mashle.toml

Run later:
  getsubtitle --config {TMP}/mashle.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-03. Japanese learner adds hiragana reading aid

- Category: `happy`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/persona_furigana_newbie.py`
- Audit focus: `terminology, reading_aids, format_default`
- Notes: Primary beginner copy path for furigana/reading-aid explanation.

<details>
<summary>Show transcript (persona_furigana_newbie)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

              Example:
              VTT:  にほんご　　べんきょう
                    日本語  を  勉強 したい

              OTHER FORMATS:  日本語(にほんご)を勉強(べんきょう)したい

    Suggested default: VTT — VTT supports positioned Japanese readings above kanji in browsers/asbplayer; local players vary.

  Final format [3 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Add pronunciation guides: Japanese hiragana readings
  • Create one Japanese + English VTT study subtitle file
  • Save to:
    {TMP}/Show

Before you run
  ⚠ VTT reading aids work best in browsers/asbplayer; local player
    support varies.

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/newbie.toml

Saved workflow:
  {TMP}/newbie.toml

Run later:
  getsubtitle --config {TMP}/newbie.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-04. Korean learner adds Revised Romanization

- Category: `happy`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/persona_korean_learner.py`
- Audit focus: `language_specific_copy, reading_aids, format_default`
- Notes: Ensures the wizard is not Japanese-only in tone or examples.

<details>
<summary>Show transcript (persona_korean_learner)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ko,en

    Languages selected:
      ko → Korean
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 한글 (hangeul)
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Korean — Revised Romanization (G2P)   [ko:revised]
       Example: 한국어 공부 → hangugeo gongbu
    3) Korean — Yale Romanization   [ko:yale]
       Example: 한국어 공부 → hankwuke kongpwu

  Numbers (comma-separated) [1 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: ASS — ASS is best for local-player stacked Korean/Chinese/Cantonese readings.

  Final format [2 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: ASS

    This output uses ASS and will usually show 3 lines at once.
    These presets are recommended:

    1) Regular (58) — recommended
    2) Smaller (46)
    3) Larger (70)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Korean, English files in:
    {TMP}/Show
  • Add pronunciation guides: Korean Revised Romanization
  • Create one Korean + English ASS study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Before you run
  ⚠ ASS shows reading aids as stacked subtitle lines. VTT is recommended
    for positioned kanji reading support in desktop browser with
    asbplayer plugin.

Smart defaults
  Display order    ko, en  (top → bottom on screen)
  Timing language  ko  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/korean.toml

Saved workflow:
  {TMP}/korean.toml

Run later:
  getsubtitle --config {TMP}/korean.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-05. Merge-only local folder

- Category: `common`
- Workflow: `merge`
- Scenario: `tests/wizard_scenarios/persona_merge_only_folder.py`
- Audit focus: `skipped_questions, defaults, output_explanation`
- Notes: A common power-user workflow that should stay short.

<details>
<summary>Show transcript (persona_merge_only_folder)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 4
    Selected: merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◼◻◻◻◻◻◻◻◻] 38%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◼◼◻◻◻◻◻] 62%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

    Japanese furigana reading aids need the Modify step (not selected yet).
  Add Modify so I can offer Japanese furigana reading aids? [Y/n | b=back | q=quit] > n
    No reading aids this run.

------------------------------------------------------------------------------------------------
Q4. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 88%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q5. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/merge-only.toml

Saved workflow:
  {TMP}/merge-only.toml

Run later:
  getsubtitle --config {TMP}/merge-only.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-06. Modify-only single subtitle file

- Category: `common`
- Workflow: `modify`
- Scenario: `tests/wizard_scenarios/persona_modify_only_single_file.py`
- Audit focus: `single_file_scope, format_choice, font_size`
- Notes: Checks that single-file input does not imply a whole season.

<details>
<summary>Show transcript (persona_modify_only_single_file)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3
    Selected: modify.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◼◻◻◻◻◻◻◻◻] 38%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Foo.ja.srt
    Selected episode: movie
    Searching for: local subtitle file: 0 video file(s), 1 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◼◼◻◻◻◻◻] 62%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja

    Languages selected:
      ja → Japanese

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 88%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese files in:
    {TMP}/Foo.ja.srt
  • Add pronunciation guides: Japanese hiragana readings
  • Save to:
    {TMP}

Smart defaults
  Cleanup preset  on  (one-line subtitles + strip broadcast noise)
  Output folder   beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/single-file.toml

Saved workflow:
  {TMP}/single-file.toml

Run later:
  getsubtitle --config {TMP}/single-file.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-07. Rename-only episode range

- Category: `common`
- Workflow: `rename`
- Scenario: `tests/wizard_scenarios/persona_rename_episodes.py`
- Audit focus: `safety_default, preview, confirmation`
- Notes: Rename is destructive-adjacent; copywriting must make copy vs original obvious.

<details>
<summary>Show transcript (persona_rename_episodes)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 5
    Selected: rename.

------------------------------------------------------------------------------------------------
Q2. Folder or file to rename.                                       Progress [◼◼◼◼◼◼◼◼◼◼◻◻◻] 75%

    Drop a season folder or one subtitle file.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 5 subtitle file(s)

Skipping 1 file(s) that don't match the
  'Title - S03E05.lang.ext' shape (left untouched):
    MF Ghost S01E03 ja.srt

Found 2 variations of files in the folder.
    1) MF Ghost - S01E**.en.srt  (2 files)
    2) MF Ghost - S01E**.ja.srt  (2 files)

  Which one would you like to work on? (1/2/3 or all) [all | b=back | q=quit] > all

Example:
  MF Ghost - S01E01.en.srt
  ------------------------
  {Title} - {Season}{Episode}.{Language}.{Modifiers}.{Extension}

What needs to be changed?
    1) Title
    2) Season
    3) Episode
    4) Language
    5) Modifiers
    6) Extension (rename only; does not convert format)

  Number [2 | b=back | q=quit] > 3

How should it be changed?
    1) Change prefix (e.g. S -> Season, E -> Ep)
    2) Change range (e.g. 01-12 -> 13-24)
    3) Change digits (e.g. 01 -> 001)

  Number [2 | b=back | q=quit] > 2

  First episode number in the new range [1 | b=back | q=quit] > 5

Planned rename: 4 file(s)
  MF Ghost - S01E01.en.srt
    -> MF Ghost - S01E05.en.srt
  MF Ghost - S01E01.ja.srt
    -> MF Ghost - S01E05.ja.srt
  MF Ghost - S01E02.en.srt
    -> MF Ghost - S01E06.en.srt
  MF Ghost - S01E02.ja.srt
    -> MF Ghost - S01E06.ja.srt

What next?
    1) Looks good — apply now
    2) Keep this change and change another field
    3) Discard this change and choose another field
    4) Cancel

  Number [1 | b=back | q=quit] > 1

How should it be applied?
    1) Copy and apply (keep the original files)
    2) Rename the original files

  Number [1 | b=back | q=quit] > 1
  Create these renamed copies? [y/N | b=back | q=quit] > y
Copied 4 renamed file(s).
```

</details>

### path-08. DeepL selected without API key

- Category: `failure`
- Workflow: `translate, modify, merge`
- Scenario: `tests/wizard_scenarios/persona_no_key_deepl.py`
- Audit focus: `setup_blocker, save_for_later, preflight`
- Notes: Failure should feel recoverable, not like a crash.

<details>
<summary>Show transcript (persona_no_key_deepl)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 2,3,4
    Selected: translate + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◻◻◻◻◻◻◻◻◻◻] 25%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◻◻◻◻◻◻◻◻] 42%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Fill missing subtitles?                                         Progress [◼◼◼◼◼◼◼◼◻◻◻◻◻] 58%

    1) Skip
    2) DeepL                  online, polished, API key required
    3) Argos                  on-device, basic quality, cross-platform
    4) Apple Translation      on-device, Mac-only, system models required
    5) Qwen3                  on-device, general-purpose local AI
    6) TranslateGemma         on-device, translation-focused local AI

    Or type any Ollama model name, e.g. translategemma:12b or qwen3:14b.

  Number or model name [1 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q5. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◼◻◻◻] 75%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q6. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q7. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 93%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Fill gaps with Deepl translation
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 1

Preflight check — 2 item(s) to know about:
  • Local subtitles found for all requested languages
      Why: Heads-up — no action needed before running.
      Fix: Fast scan checked 2 subtitle candidate(s).
  ✗ DeepL API key
      Why: Required — the run would fail before it starts.
      Fix: getsubtitle --set-key deepl
  Show setup steps for the blocker(s)? [Y/n] > y

Setup — let's fill in the missing pieces.

  ✗ DeepL API key
      Suggested fix: getsubtitle --set-key deepl
      Run `--set-key deepl` now? [Y/n] > n


I can't run this workflow yet because the required setup is still missing.
Still blocked — the run would fail before it starts:
  What: DeepL API key
  Why:  Required for this workflow.
  How:  getsubtitle --set-key deepl
  Save a reusable workflow file to run after setup? [y/N] > y
  Saving a workflow file now. You can run it later with `getsubtitle --config FILE.toml`.


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/deepl-later.toml

Saved workflow:
  {TMP}/deepl-later.toml

Run later:
  getsubtitle --config {TMP}/deepl-later.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-09. Ollama selected but daemon/model unavailable

- Category: `failure`
- Workflow: `translate, modify, merge`
- Scenario: `tests/wizard_scenarios/persona_ollama_down.py`
- Audit focus: `setup_blocker, local_dependency, save_for_later`
- Notes: Good test for plain-English dependency copy.

<details>
<summary>Show transcript (persona_ollama_down)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 2,3,4
    Selected: translate + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◻◻◻◻◻◻◻◻◻◻] 25%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◻◻◻◻◻◻◻◻] 42%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Fill missing subtitles?                                         Progress [◼◼◼◼◼◼◼◼◻◻◻◻◻] 58%

    1) Skip
    2) DeepL                  online, polished, API key required
    3) Argos                  on-device, basic quality, cross-platform
    4) Apple Translation      on-device, Mac-only, system models required
    5) Qwen3                  on-device, general-purpose local AI
    6) TranslateGemma         on-device, translation-focused local AI

    Or type any Ollama model name, e.g. translategemma:12b or qwen3:14b.

  Number or model name [1 | b=back | q=quit] > 5

------------------------------------------------------------------------------------------------
Q5. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◼◻◻◻] 75%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q6. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q7. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 93%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Fill gaps with Ollama (qwen3:8b) translation
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 1

Preflight check — 2 item(s) to know about:
  • Local subtitles found for all requested languages
      Why: Heads-up — no action needed before running.
      Fix: Fast scan checked 2 subtitle candidate(s).
  ✗ Ollama daemon at http://localhost:11434
      Why: Required — the run would fail before it starts.
      Fix: Start Ollama: https://ollama.com  (then re-run)
  Show setup steps for the blocker(s)? [Y/n] > y

Setup — let's fill in the missing pieces.

  ✗ Ollama daemon at http://localhost:11434
      Suggested fix: Start Ollama: https://ollama.com  (then re-run)
    (Manual step — re-launch the wizard once done.)


I can't run this workflow yet because the required setup is still missing.
Still blocked — the run would fail before it starts:
  What: Ollama daemon at http://localhost:11434
  Why:  Required for this workflow.
  How:  Start Ollama: https://ollama.com  (then re-run)
  Save a reusable workflow file to run after setup? [y/N] > y
  Saving a workflow file now. You can run it later with `getsubtitle --config FILE.toml`.


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/ollama-later.toml

Saved workflow:
  {TMP}/ollama-later.toml

Run later:
  getsubtitle --config {TMP}/ollama-later.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-10. Requested language missing from local folder

- Category: `edge`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/persona_wrong_lang.py`
- Audit focus: `missing_explanation, manual_search, recovery`
- Notes: Should teach the user what the folder contains and what to try next.

<details>
<summary>Show transcript (persona_wrong_lang)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Foo
    Searching for: local subtitle folder: 0 video file(s), 1 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

    Local subtitle check:
      Found locally: ko
      Missing for your requested stack: ja, en
    If you continue without Fetch, modify/merge can only use the
    subtitle languages already in this folder.
  Search online for the missing languages now? [Y/n | b=back | q=quit] > n
    Tip: restart with `getsubtitle -i`, choose Fetch, and use a
    catalog URL/title so getsubtitle can look online for missing tracks.

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Foo
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Foo

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > q
Quit.
```

</details>

### path-11. Skip AI translation intentionally

- Category: `edge`
- Workflow: `fetch, modify, merge`
- Scenario: `tests/wizard_scenarios/trap_skip_mt_no_scold.py`
- Audit focus: `tone, warnings, no_scolding`
- Notes: Skipping AI translation is a valid choice; warnings should not sound like errors.

<details>
<summary>Show transcript (trap_skip_mt_no_scold)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 1,2,3,4
    Selected: fetch + translate + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Where should we get subtitles from?                             Progress [◼◼◻◻◻◻◻◻◻◻◻◻◻] 19%

    1) A movie/show title (The Simpsons, Totoro, The Matrix, …)
    2) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)
    3) A folder or file on disk (your Plex/Movies, ~/Downloads, …)

  Number [3 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q3. Enter the URL.                                                  Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 31%

  URL [b=back | q=quit] > https://www.imdb.com/title/tt28299608/
    Searching for: IMDb title URL

------------------------------------------------------------------------------------------------
Q4. What episode scope?                                             Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 44%

    1) Specific season + episode (or range)
       Defaults to Season 1 Episode 1.
    2) Whole season, every episode (-e all)
    3) Auto — let getsubtitle infer from the URL/title metadata
       (anime URLs typically resolve to single episodes; movies to a
        single item; TV without -e usually picks S01E01)

  Number [3 | b=back | q=quit] > 3

------------------------------------------------------------------------------------------------
Q5. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◼◻◻◻◻◻◻] 56%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q6. Fill missing subtitles?                                         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 69%

    1) Skip
    2) DeepL                  online, polished, API key required
    3) Argos                  on-device, basic quality, cross-platform
    4) Apple Translation      on-device, Mac-only, system models required
    5) Qwen3                  on-device, general-purpose local AI
    6) TranslateGemma         on-device, translation-focused local AI

    Or type any Ollama model name, e.g. translategemma:12b or qwen3:14b.

  Number or model name [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q7. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 81%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q8. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 94%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q9. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 94%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Fetch Japanese, English for:
    https://www.imdb.com/title/tt28299608/
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    ~/Downloads/GetSubtitle

Before you run
  ⚠ Japanese subtitles can be harder to find automatically; manual
    search or translation may be needed.

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    ~/Downloads/GetSubtitle

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [4 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/saved.toml

Saved workflow:
  {TMP}/saved.toml

Run later:
  getsubtitle --config {TMP}/saved.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-12. Crunchyroll season page with absolute episode numbers

- Category: `edge`
- Workflow: `fetch, modify, merge`
- Scenario: `tests/wizard_scenarios/trap_crunchyroll_auto_scope_requires_range.py`
- Audit focus: `episode_scope, numbering, examples`
- Notes: Most important scope copy for anime streaming pages.

<details>
<summary>Show transcript (trap_crunchyroll_auto_scope_requires_range)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 1,3,4
    Selected: fetch + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Where should we get subtitles from?                             Progress [◼◼◼◻◻◻◻◻◻◻◻◻◻] 21%

    1) A movie/show title (The Simpsons, Totoro, The Matrix, …)
    2) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)
    3) A folder or file on disk (your Plex/Movies, ~/Downloads, …)

  Number [3 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q3. Enter the URL.                                                  Progress [◼◼◼◼◼◻◻◻◻◻◻◻◻] 36%

  URL [b=back | q=quit] > https://www.crunchyroll.com/watch/GZ7UDVKPD/miraculous-comeback
    Searching for: Crunchyroll watch URL

    Crunchyroll metadata found:
      Series: MF GHOST
      Episode: Miraculous Comeback
      Scope: S3 E25
    Using Crunchyroll series URL: https://www.crunchyroll.com/series/GEXH3W2W7/mf-ghost

------------------------------------------------------------------------------------------------
Q4. What episode scope?                                             Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    1) Specific season + episode (or range)
       Defaults to Season 1 Episode 1.
    2) Whole season, every episode (-e all)
    3) Auto — let getsubtitle infer from the URL/title metadata
       (anime URLs typically resolve to single episodes; movies to a
        single item; TV without -e usually picks S01E01)

    Crunchyroll may display Season 3 as E25-E37, but subtitle
    sources usually search that as Season 3 episodes 1-13.

  Number [1 | b=back | q=quit] > 1

  Season or range (e.g. 1, 2-3, all) [1 | b=back | q=quit] > 3

  Episode or range within each season (e.g. 5, 1-10, all) [1 | b=back | q=quit] > 1-13

------------------------------------------------------------------------------------------------
Q5. How should episode numbers appear in output filenames?          Progress [◼◼◼◼◼◼◼◼◻◻◻◻◻] 64%

    You are searching Season 3 episode(s): 1-13.
    Some streaming pages continue numbering across seasons, while
    subtitle sources often restart from episode 1 inside each season.

    1) Start filenames at E1 for this season
       Example: S03E01, S03E02, ...
    2) Match the episode numbers shown on the streaming page
       Example: S03E25, S03E26, ...

  Number [1 | b=back | q=quit] > 2

  First episode number shown on the page (e.g. 25) [b=back | q=quit] > 25
    Output filenames will start at S03E25.

------------------------------------------------------------------------------------------------
Q6. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◼◼◼◼◻◻◻] 79%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,ko

    Languages selected:
      ja → Japanese
      ko → Korean

------------------------------------------------------------------------------------------------
Q7. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 93%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai
    5) Korean — Revised Romanization (G2P)   [ko:revised]
       Example: 한국어 공부 → hangugeo gongbu
    6) Korean — Yale Romanization   [ko:yale]
       Example: 한국어 공부 → hankwuke kongpwu

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q8. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 94%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q9. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 94%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Fetch Japanese, Korean for:
    MF GHOST  (season 3, episode 1-13)
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + Korean SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    ~/Downloads/GetSubtitle

Before you run
  ⚠ Japanese, Korean subtitles can be harder to find automatically;
    manual search or translation may be needed.

Smart defaults
  Display order    ja, ko  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    ~/Downloads/GetSubtitle

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [4 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/mfghost-s3.toml

Saved workflow:
  {TMP}/mfghost-s3.toml

Run later:
  getsubtitle --config {TMP}/mfghost-s3.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-13. Local video file should scope to one episode

- Category: `edge`
- Workflow: `fetch, modify, merge`
- Scenario: `tests/wizard_scenarios/trap_local_file_scopes_to_episode.py`
- Audit focus: `single_file_scope, surprise_prevention`
- Notes: Regression guard against accidentally scanning a whole season.

<details>
<summary>Show transcript (trap_local_file_scopes_to_episode)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show/Show.S02E05.1080p.WEB-DL.mp4
    Selected episode: S02E05
    File selected; using its folder so matching subtitle files can be found.
    Searching for: local folder beside selected file: 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > q
Quit.
```

</details>

### path-14. Open folder after run

- Category: `edge`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/trap_open_folder_only_opens.py`
- Audit focus: `post_run_action, side_effects`
- Notes: Protects against the old double-dispatch bug.

<details>
<summary>Show transcript (trap_open_folder_only_opens)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 1

Preflight check — 1 item(s) to know about:
  • Local subtitles found for all requested languages
      Why: Heads-up — no action needed before running.
      Fix: Fast scan checked 2 subtitle candidate(s).

------------------------------------------------------------------------------------------------
Running:
  getsubtitle --source {TMP}/Show --modify --strip-cc-noise --single-line --merge --languages ja,en --format srt --font-size regular --output {TMP}/Show


======================================================================
Workflow summary
======================================================================
Completed successfully

Next steps:
  1. Merge later with: getsubtitle merge {TMP}/Show -l ja,en
  2. Re-run this workflow command after any setup fixes:
     getsubtitle --source {TMP}/Show --modify --strip-cc-noise --single-line --merge --languages ja,en --format srt --font-size regular --output {TMP}/Show
  Open folder? [Y/n] > y
```

</details>

### path-15. Finder drag-drop quoted path

- Category: `common`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/persona_drag_quoted.py`
- Audit focus: `path_validation, beginner_input`
- Notes: Mac users commonly paste paths wrapped in quotes.

<details>
<summary>Show transcript (persona_drag_quoted)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > '{TMP}/Shows/Foo Bar'
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Shows/Foo Bar
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Shows/Foo Bar

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/drag.toml

Saved workflow:
  {TMP}/drag.toml

Run later:
  getsubtitle --config {TMP}/drag.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-16. Quoted path stripped before validation

- Category: `edge`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/trap_quoted_path_stripped.py`
- Audit focus: `path_validation, error_prevention`
- Notes: A tighter regression trap for quoted path handling.

<details>
<summary>Show transcript (trap_quoted_path_stripped)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > '{TMP}/Foo Bar'
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Foo Bar
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Foo Bar

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > q
Quit.
```

</details>

### path-17. Free text entered at Q1 instead of choosing a mode

- Category: `failure`
- Workflow: `fetch, modify, merge`
- Scenario: `tests/wizard_scenarios/persona_title_typo_at_q1.py`
- Audit focus: `invalid_selection, recovery, plain_language`
- Notes: Checks that the error explains how to search by title.

<details>
<summary>Show transcript (persona_title_typo_at_q1)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] >
    Selected: fetch + translate + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Where should we get subtitles from?                             Progress [◼◼◻◻◻◻◻◻◻◻◻◻◻] 19%

    1) A movie/show title (The Simpsons, Totoro, The Matrix, …)
    2) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)
    3) A folder or file on disk (your Plex/Movies, ~/Downloads, …)

  Number [3 | b=back | q=quit] > totoro
    Detected title search:
      totoro

    Searching for: 'totoro'

    No title matches found.
    I won't build a fetch workflow from an unverified title yet.
    Check the spelling, paste an IMDb/TMDB/AniList URL, or choose
    the raw-title escape only if you know the title source works.

    Add a TMDB key for richer movie/TV matches:
      getsubtitle --set-key tmdb

    1) Re-enter a different title
    2) Use exactly what I typed (advanced; may fail)

  Number, URL, ID, or title [1 | b=back | q=quit] > 2
  Is this a movie? (No = TV show / anime) [y/N | b=back | q=quit] > n

------------------------------------------------------------------------------------------------
Q3. What episode scope?                                             Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 31%

    1) Specific season + episode (or range)
       Defaults to Season 1 Episode 1.
    2) Whole season, every episode (-e all)
    3) Auto — let getsubtitle infer from the URL/title metadata
       (anime URLs typically resolve to single episodes; movies to a
        single item; TV without -e usually picks S01E01)

  Number [3 | b=back | q=quit] > 2
    (Note: -e all on non-anime TV requires a TMDB key. Run `getsubtitle --set-key tmdb` later if needed.)

------------------------------------------------------------------------------------------------
Q4. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 44%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > 1
    I don't recognize: 1
    Use 2-letter codes or full names, like ja,en or japanese,korean,english.
    Type 'g' for the full language guide.

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > 1
    I don't recognize: 1
    Use 2-letter codes or full names, like ja,en or japanese,korean,english.
    Type 'g' for the full language guide.

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q5. Fill missing subtitles?                                         Progress [◼◼◼◼◼◼◼◻◻◻◻◻◻] 56%

    1) Skip
    2) DeepL                  online, polished, API key required
    3) Argos                  on-device, basic quality, cross-platform
    4) Apple Translation      on-device, Mac-only, system models required
    5) Qwen3                  on-device, general-purpose local AI
    6) TranslateGemma         on-device, translation-focused local AI

    Or type any Ollama model name, e.g. translategemma:12b or qwen3:14b.

  Number or model name [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q6. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 69%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q7. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 81%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q8. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 83%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Fetch Japanese, English for:
    totoro  (season 1, episode all)
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    ~/Downloads/GetSubtitle

Before you run
  ⚠ Japanese subtitles can be harder to find automatically; manual
    search or translation may be needed.

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    ~/Downloads/GetSubtitle

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [4 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/totoro-typo.toml

Saved workflow:
  {TMP}/totoro-typo.toml

Run later:
  getsubtitle --config {TMP}/totoro-typo.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-18. Q1 rejects free text and recovers

- Category: `failure`
- Workflow: `fetch, modify, merge`
- Scenario: `tests/wizard_scenarios/trap_q1_rejects_free_text.py`
- Audit focus: `invalid_selection, default_safety`
- Notes: Similar to path 17 but covers the trap path explicitly.

<details>
<summary>Show transcript (trap_q1_rejects_free_text)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] >
    Selected: fetch + translate + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Where should we get subtitles from?                             Progress [◼◼◻◻◻◻◻◻◻◻◻◻◻] 19%

    1) A movie/show title (The Simpsons, Totoro, The Matrix, …)
    2) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)
    3) A folder or file on disk (your Plex/Movies, ~/Downloads, …)

  Number [3 | b=back | q=quit] > totoro
    Detected title search:
      totoro

    Searching for: 'totoro'

    No title matches found.
    I won't build a fetch workflow from an unverified title yet.
    Check the spelling, paste an IMDb/TMDB/AniList URL, or choose
    the raw-title escape only if you know the title source works.

    Add a TMDB key for richer movie/TV matches:
      getsubtitle --set-key tmdb

    1) Re-enter a different title
    2) Use exactly what I typed (advanced; may fail)

  Number, URL, ID, or title [1 | b=back | q=quit] > 2
  Is this a movie? (No = TV show / anime) [y/N | b=back | q=quit] > n

------------------------------------------------------------------------------------------------
Q3. What episode scope?                                             Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 31%

    1) Specific season + episode (or range)
       Defaults to Season 1 Episode 1.
    2) Whole season, every episode (-e all)
    3) Auto — let getsubtitle infer from the URL/title metadata
       (anime URLs typically resolve to single episodes; movies to a
        single item; TV without -e usually picks S01E01)

  Number [3 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q4. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 44%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q5. Fill missing subtitles?                                         Progress [◼◼◼◼◼◼◼◻◻◻◻◻◻] 56%

    1) Skip
    2) DeepL                  online, polished, API key required
    3) Argos                  on-device, basic quality, cross-platform
    4) Apple Translation      on-device, Mac-only, system models required
    5) Qwen3                  on-device, general-purpose local AI
    6) TranslateGemma         on-device, translation-focused local AI

    Or type any Ollama model name, e.g. translategemma:12b or qwen3:14b.

  Number or model name [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q6. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 69%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q7. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 81%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q8. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 83%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Fetch Japanese, English for:
    totoro
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    ~/Downloads/GetSubtitle

Before you run
  ⚠ Japanese subtitles can be harder to find automatically; manual
    search or translation may be needed.

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    ~/Downloads/GetSubtitle

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [4 | b=back | q=quit] > q
Quit.
```

</details>

### path-19. Back navigation through a previous step

- Category: `edge`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/persona_back_navigation.py`
- Audit focus: `back_navigation, state_reset`
- Notes: Back should move one logical question, not lose unrelated answers.

<details>
<summary>Show transcript (persona_back_navigation)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Wrong
    Searching for: local subtitle folder: 0 video file(s), 1 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > b
    Going back to the previous step.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Right
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Right
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Right

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/back.toml

Saved workflow:
  {TMP}/back.toml

Run later:
  getsubtitle --config {TMP}/back.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-20. Start-over selected but user declines discard

- Category: `edge`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/persona_restart_decline.py`
- Audit focus: `destructive_confirmation, draft_safety`
- Notes: Restart is a destructive workflow action and needs confirmation.

<details>
<summary>Show transcript (persona_restart_decline)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 5
  Discard all answers and start over? [y/N | b=back | q=quit] > n

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > q
Quit.
```

</details>

### path-21. Change a setting from final screen

- Category: `edge`
- Workflow: `modify`
- Scenario: `tests/wizard_scenarios/persona_power_edit.py`
- Audit focus: `edit_flow, state_reset, numbering`
- Notes: Covers the final-action edit branch.

<details>
<summary>Show transcript (persona_power_edit)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 2

Current settings
  1) steps: modify + merge
  2) source: path — {TMP}/Show
  3) languages: ja, en
  4) display order: ja, en
  5) timing language: ja
  6) cleanup preset: on
  7) reading aids: none
  8) format / extension: SRT
  9) text size: regular
  10) output folder: {TMP}/Show

  Number to change (1-10), or 'done' [done | b=back | q=quit] > 1
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3
    Selected: modify.

Current settings
  1) steps: modify
  2) source: path — {TMP}/Show
  3) languages: ja, en
  4) cleanup preset: on
  5) reading aids: none
  6) output folder: {TMP}/Show

  Number to change (1-6), or 'done' [done | b=back | q=quit] > done

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Save to:
    {TMP}/Show

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/edited.toml

Saved workflow:
  {TMP}/edited.toml

Run later:
  getsubtitle --config {TMP}/edited.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-22. Save reusable TOML, then override later

- Category: `common`
- Workflow: `fetch, modify, merge`
- Scenario: `tests/wizard_scenarios/persona_re_runner.py`
- Audit focus: `toml_reuse, override_explanation`
- Notes: Important copy for non-programmers learning what a workflow file does.

<details>
<summary>Show transcript (persona_re_runner)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 1,3,4
    Selected: fetch + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Where should we get subtitles from?                             Progress [◼◼◼◻◻◻◻◻◻◻◻◻◻] 21%

    1) A movie/show title (The Simpsons, Totoro, The Matrix, …)
    2) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)
    3) A folder or file on disk (your Plex/Movies, ~/Downloads, …)

  Number [3 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q3. Enter the URL.                                                  Progress [◼◼◼◼◼◻◻◻◻◻◻◻◻] 36%

  URL [b=back | q=quit] > https://www.imdb.com/title/tt28299608/
    Searching for: IMDb title URL

------------------------------------------------------------------------------------------------
Q4. What episode scope?                                             Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    1) Specific season + episode (or range)
       Defaults to Season 1 Episode 1.
    2) Whole season, every episode (-e all)
    3) Auto — let getsubtitle infer from the URL/title metadata
       (anime URLs typically resolve to single episodes; movies to a
        single item; TV without -e usually picks S01E01)

  Number [3 | b=back | q=quit] > 2
    (Note: -e all on non-anime TV requires a TMDB key. Run `getsubtitle --set-key tmdb` later if needed.)

------------------------------------------------------------------------------------------------
Q5. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◼◼◻◻◻◻◻] 64%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > 1
    I don't recognize: 1
    Use 2-letter codes or full names, like ja,en or japanese,korean,english.
    Type 'g' for the full language guide.

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > 1
    I don't recognize: 1
    Use 2-letter codes or full names, like ja,en or japanese,korean,english.
    Type 'g' for the full language guide.

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q6. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◼◻◻◻] 79%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q7. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 93%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q8. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 94%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Fetch Japanese, English for:
    https://www.imdb.com/title/tt28299608/  (season 1, episode all)
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    ~/Downloads/GetSubtitle

Before you run
  ⚠ Japanese subtitles can be harder to find automatically; manual
    search or translation may be needed.

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    ~/Downloads/GetSubtitle

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [4 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/saved.toml

Saved workflow:
  {TMP}/saved.toml

Run later:
  getsubtitle --config {TMP}/saved.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-23. TOML save includes override hint and open-folder prompt

- Category: `edge`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/trap_toml_save_reuse_hint.py`
- Audit focus: `toml_reuse, open_folder, examples`
- Notes: Pins the post-save educational copy.

<details>
<summary>Show transcript (trap_toml_save_reuse_hint)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/Reusable.toml

Saved workflow:
  {TMP}/Reusable.toml

Run later:
  getsubtitle --config {TMP}/Reusable.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > 1

Exact command:
  # getsubtitle --source {TMP}/Show --modify --strip-cc-noise --single-line --merge --languages ja,en --format srt --font-size regular --output {TMP}/Show

You can recycle this TOML and override saved settings with extra CLI flags.
For example, reuse the same language, reading-aid, translation, and merge
choices on another show or season:
  getsubtitle --config {TMP}/Reusable.toml --source 'https://www.imdb.com/title/tt1234567/' --season 3 --episode all --output "$HOME/Downloads/GetSubtitle/TV Show/Season 03"

CLI flags win over matching TOML settings, so the file can stay as a reusable template.

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > 2

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > 3
```

</details>

### path-24. URL-first fetch workflow

- Category: `common`
- Workflow: `fetch, modify, merge`
- Scenario: `tests/wizard_scenarios/persona_url_first.py`
- Audit focus: `source_type, scope, provider_expectations`
- Notes: Common path for users who do not have local subtitle files yet.

<details>
<summary>Show transcript (persona_url_first)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 1,3,4
    Selected: fetch + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Where should we get subtitles from?                             Progress [◼◼◼◻◻◻◻◻◻◻◻◻◻] 21%

    1) A movie/show title (The Simpsons, Totoro, The Matrix, …)
    2) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)
    3) A folder or file on disk (your Plex/Movies, ~/Downloads, …)

  Number [3 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q3. Enter the URL.                                                  Progress [◼◼◼◼◼◻◻◻◻◻◻◻◻] 36%

  URL [b=back | q=quit] > https://www.imdb.com/title/tt28299608/
    Searching for: IMDb title URL

------------------------------------------------------------------------------------------------
Q4. What episode scope?                                             Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    1) Specific season + episode (or range)
       Defaults to Season 1 Episode 1.
    2) Whole season, every episode (-e all)
    3) Auto — let getsubtitle infer from the URL/title metadata
       (anime URLs typically resolve to single episodes; movies to a
        single item; TV without -e usually picks S01E01)

  Number [3 | b=back | q=quit] > 2
    (Note: -e all on non-anime TV requires a TMDB key. Run `getsubtitle --set-key tmdb` later if needed.)

------------------------------------------------------------------------------------------------
Q5. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◼◼◻◻◻◻◻] 64%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > 1
    I don't recognize: 1
    Use 2-letter codes or full names, like ja,en or japanese,korean,english.
    Type 'g' for the full language guide.

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > 1
    I don't recognize: 1
    Use 2-letter codes or full names, like ja,en or japanese,korean,english.
    Type 'g' for the full language guide.

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q6. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◼◻◻◻] 79%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q7. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 93%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

              Example:
              VTT:  にほんご　　べんきょう
                    日本語  を  勉強 したい

              OTHER FORMATS:  日本語(にほんご)を勉強(べんきょう)したい

    Suggested default: VTT — VTT supports positioned Japanese readings above kanji in browsers/asbplayer; local players vary.

  Final format [3 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Fetch Japanese, English for:
    https://www.imdb.com/title/tt28299608/  (season 1, episode all)
  • Add pronunciation guides: Japanese hiragana readings
  • Create one Japanese + English VTT study subtitle file
  • Save to:
    ~/Downloads/GetSubtitle

Before you run
  ⚠ Japanese subtitles can be harder to find automatically; manual
    search or translation may be needed.
  ⚠ VTT reading aids work best in browsers/asbplayer; local player
    support varies.

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    ~/Downloads/GetSubtitle

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [4 | b=back | q=quit] >


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/url-first.toml

Saved workflow:
  {TMP}/url-first.toml

Run later:
  getsubtitle --config {TMP}/url-first.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-25. DeepL engine maps correctly in CLI/TOML

- Category: `edge`
- Workflow: `fetch, translate, modify, merge`
- Scenario: `tests/wizard_scenarios/trap_engine_mapping_deepl_emits_deepl.py`
- Audit focus: `terminology, engine_mapping`
- Notes: Protects against Argos/DeepL wording and emission mixups.

<details>
<summary>Show transcript (trap_engine_mapping_deepl_emits_deepl)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 1,2,3,4
    Selected: fetch + translate + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Where should we get subtitles from?                             Progress [◼◼◻◻◻◻◻◻◻◻◻◻◻] 19%

    1) A movie/show title (The Simpsons, Totoro, The Matrix, …)
    2) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)
    3) A folder or file on disk (your Plex/Movies, ~/Downloads, …)

  Number [3 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q3. Enter the URL.                                                  Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 31%

  URL [b=back | q=quit] > https://www.imdb.com/title/tt28299608/
    Searching for: IMDb title URL

------------------------------------------------------------------------------------------------
Q4. What episode scope?                                             Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 44%

    1) Specific season + episode (or range)
       Defaults to Season 1 Episode 1.
    2) Whole season, every episode (-e all)
    3) Auto — let getsubtitle infer from the URL/title metadata
       (anime URLs typically resolve to single episodes; movies to a
        single item; TV without -e usually picks S01E01)

  Number [3 | b=back | q=quit] > 3

------------------------------------------------------------------------------------------------
Q5. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◼◻◻◻◻◻◻] 56%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q6. Fill missing subtitles?                                         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 69%

    1) Skip
    2) DeepL                  online, polished, API key required
    3) Argos                  on-device, basic quality, cross-platform
    4) Apple Translation      on-device, Mac-only, system models required
    5) Qwen3                  on-device, general-purpose local AI
    6) TranslateGemma         on-device, translation-focused local AI

    Or type any Ollama model name, e.g. translategemma:12b or qwen3:14b.

  Number or model name [1 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q7. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 81%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q8. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 94%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q9. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 94%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Fetch Japanese, English for:
    https://www.imdb.com/title/tt28299608/
  • Fill gaps with Deepl translation
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    ~/Downloads/GetSubtitle

Before you run
  ⚠ Japanese subtitles can be harder to find automatically; manual
    search or translation may be needed.

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    ~/Downloads/GetSubtitle

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [4 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/deepl-flow.toml

Saved workflow:
  {TMP}/deepl-flow.toml

Run later:
  getsubtitle --config {TMP}/deepl-flow.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-26. Enter accepts defaults at yes/no and menu prompts

- Category: `edge`
- Workflow: `fetch, translate, modify, merge`
- Scenario: `tests/wizard_scenarios/trap_enter_accepts_default.py`
- Audit focus: `default_prompt, enter_behavior`
- Notes: Important for confidence: displayed defaults must actually work.

<details>
<summary>Show transcript (trap_enter_accepts_default)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] >
    Selected: fetch + translate + modify + merge.

------------------------------------------------------------------------------------------------
Q2. Where should we get subtitles from?                             Progress [◼◼◻◻◻◻◻◻◻◻◻◻◻] 19%

    1) A movie/show title (The Simpsons, Totoro, The Matrix, …)
    2) A streaming/catalog URL (IMDb, AniList, Netflix, Crunchyroll, …)
    3) A folder or file on disk (your Plex/Movies, ~/Downloads, …)

  Number [3 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q3. Enter the folder or file path.                                  Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 31%

  Folder or file path [b=back | q=quit] > {TMP}/Foo
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q4. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 44%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] >

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q5. Fill missing subtitles?                                         Progress [◼◼◼◼◼◼◼◻◻◻◻◻◻] 56%

    1) Skip
    2) DeepL                  online, polished, API key required
    3) Argos                  on-device, basic quality, cross-platform
    4) Apple Translation      on-device, Mac-only, system models required
    5) Qwen3                  on-device, general-purpose local AI
    6) TranslateGemma         on-device, translation-focused local AI

    Or type any Ollama model name, e.g. translategemma:12b or qwen3:14b.

  Number or model name [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 69%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q7. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 81%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q8. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 83%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Fetch Japanese, English for:
    {TMP}/Foo
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Foo

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] >

Preflight check — 1 item(s) to know about:
  • Local subtitles found for all requested languages
      Why: Heads-up — no action needed before running.
      Fix: Fast scan checked 2 subtitle candidate(s).

------------------------------------------------------------------------------------------------
Running:
  getsubtitle --fetch {TMP}/Foo --languages ja,en --modify --strip-cc-noise --single-line --merge --format srt --font-size regular --output {TMP}/Foo


======================================================================
Workflow summary
======================================================================
Completed successfully

Next steps:
  1. Merge later with: getsubtitle merge {TMP}/Foo -l ja,en
  2. Re-run this workflow command after any setup fixes:
     getsubtitle --fetch {TMP}/Foo --languages ja,en --modify --strip-cc-noise --single-line --merge --format srt --font-size regular --output {TMP}/Foo
  Open folder? [Y/n] >
```

</details>

### path-27. Japanese hiragana reading aid defaults to VTT

- Category: `edge`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/trap_format_default_vtt_for_ja_hiragana.py`
- Audit focus: `format_default, player_limitations`
- Notes: Needs careful copy because VTT can show positioned Japanese readings in asbplayer but is uneven elsewhere.

<details>
<summary>Show transcript (trap_format_default_vtt_for_ja_hiragana)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 2

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

              Example:
              VTT:  にほんご　　べんきょう
                    日本語  を  勉強 したい

              OTHER FORMATS:  日本語(にほんご)を勉強(べんきょう)したい

    Suggested default: VTT — VTT supports positioned Japanese readings above kanji in browsers/asbplayer; local players vary.

  Final format [3 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Add pronunciation guides: Japanese hiragana readings
  • Create one Japanese + English VTT study subtitle file
  • Save to:
    {TMP}/Show

Before you run
  ⚠ VTT reading aids work best in browsers/asbplayer; local player
    support varies.

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/vtt-ja.toml

Saved workflow:
  {TMP}/vtt-ja.toml

Run later:
  getsubtitle --config {TMP}/vtt-ja.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-28. Modify+merge local path emits positional CLI correctly

- Category: `edge`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/trap_modify_merge_no_fetch_uses_positional_path.py`
- Audit focus: `cli_equivalence, source_override`
- Notes: Prevents confusing generated commands.

<details>
<summary>Show transcript (trap_modify_merge_no_fetch_uses_positional_path)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > q
Quit.
```

</details>

### path-29. Movie folder workflow

- Category: `common`
- Workflow: `fetch, modify, merge`
- Scenario: `tests/wizard_scenarios/persona_folder_movie.py`
- Audit focus: `movie_scope, episode_labels`
- Notes: Checks movie-shaped filenames and S00E00 behavior.

<details>
<summary>Show transcript (persona_folder_movie)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 4
    Selected: merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◼◻◻◻◻◻◻◻◻] 38%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Totoro
    Searching for: local subtitle folder: 0 video file(s), 2 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◼◼◻◻◻◻◻] 62%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

    Japanese furigana reading aids need the Modify step (not selected yet).
  Add Modify so I can offer Japanese furigana reading aids? [Y/n | b=back | q=quit] > n
    No reading aids this run.

------------------------------------------------------------------------------------------------
Q4. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 88%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q5. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Totoro
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Totoro

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 4


  Save to (relative paths OK) [getsubtitle-workflow.toml] > {TMP}/totoro.toml

Saved workflow:
  {TMP}/totoro.toml

Run later:
  getsubtitle --config {TMP}/totoro.toml

    1) Show exact command
    2) Open containing folder
    3) Done

  Number [3] > n
```

</details>

### path-30. Existing merged output detected before run

- Category: `failure`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/trap_existing_merge_output_preflight.py`
- Audit focus: `overwrite_safety, preflight, plain_language`
- Notes: Warns before dispatch so the user understands why merge may skip writing.

<details>
<summary>Show transcript (trap_existing_merge_output_preflight)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 3 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 1

Preflight check — 2 item(s) to know about:
  • Local subtitles found for all requested languages
      Why: Heads-up — no action needed before running.
      Fix: Fast scan checked 3 subtitle candidate(s).
  • Existing output files detected for 1/1 selected episode(s)
      Why: Optional — the run works, but may fail or look worse without it.
      Fix: S01E01 -> Show - S01E01.ja-en.srt. Choose a different output folder, remove old files, or run from CLI with --force.

------------------------------------------------------------------------------------------------
Running:
  getsubtitle --source {TMP}/Show --modify --strip-cc-noise --single-line --merge --languages ja,en --format srt --font-size regular --output {TMP}/Show


======================================================================
Workflow summary
======================================================================
Completed successfully

Next steps:
  1. Merge later with: getsubtitle merge {TMP}/Show -l ja,en
  2. Re-run this workflow command after any setup fixes:
     getsubtitle --source {TMP}/Show --modify --strip-cc-noise --single-line --merge --languages ja,en --format srt --font-size regular --output {TMP}/Show
  Open folder? [Y/n] > n
```

</details>

### path-31. Partial local subtitle coverage detected before run

- Category: `edge`
- Workflow: `modify, merge`
- Scenario: `tests/wizard_scenarios/trap_partial_local_coverage_preflight.py`
- Audit focus: `partial_coverage, missing_explanation, preflight`
- Notes: Shows missing episode/language examples before the command runs.

<details>
<summary>Show transcript (trap_partial_local_coverage_preflight)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 3,4
    Selected: modify + merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◻◻◻◻◻◻◻◻◻] 30%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local subtitle folder: 0 video file(s), 3 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◻◻◻◻◻◻◻] 50%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

------------------------------------------------------------------------------------------------
Q4. Reading aids (phonetic guides for the original script).         Progress [◼◼◼◼◼◼◼◼◼◻◻◻◻] 70%

    Example output: 漢字（かんじ）
    Pick any combination by number, or '1' to skip.
    1) No reading aid (skip)
    2) Japanese — hiragana readings for kanji   [ja:hiragana]
       Example: 勉強する → べんきょうする
    3) Japanese — katakana readings for kanji   [ja:katakana]
       Example: 勉強する → ベンキョウする
    4) Japanese — full-sentence romaji   [ja:romaji]
       Example: 今日は日本語を練習したい → kyou wa nihongo wo renshuu shitai

  Numbers (comma-separated) [1 | b=back | q=quit] > 1

------------------------------------------------------------------------------------------------
Q5. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q6. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 92%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Clean up subtitle lines (single line, strip broadcast noise)
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 1

Preflight check — 1 item(s) to know about:
  • Some requested subtitles are not in this folder yet
      Why: Optional — the run works, but may fail or look worse without it.
      Fix: Local subtitles found: Japanese, English; S01E02 missing en

------------------------------------------------------------------------------------------------
Running:
  getsubtitle --source {TMP}/Show --modify --strip-cc-noise --single-line --merge --languages ja,en --format srt --font-size regular --output {TMP}/Show


======================================================================
Workflow summary
======================================================================
Completed successfully

Next steps:
  1. Merge later with: getsubtitle merge {TMP}/Show -l ja,en
  2. Re-run this workflow command after any setup fixes:
     getsubtitle --source {TMP}/Show --modify --strip-cc-noise --single-line --merge --languages ja,en --format srt --font-size regular --output {TMP}/Show
  Open folder? [Y/n] > n
```

</details>

### path-32. No local subtitles found before run

- Category: `failure`
- Workflow: `merge`
- Scenario: `tests/wizard_scenarios/trap_no_local_subtitles_preflight.py`
- Audit focus: `no_subtitles, mkv_extraction, recovery`
- Notes: Explains that the folder has no subtitle files and hints at extraction/fetch.

<details>
<summary>Show transcript (trap_no_local_subtitles_preflight)</summary>

```text
  ____      _   ____        _     _   _ _   _
 / ___| ___| |_/ ___| _   _| |__ | |_| |_| |_| ___
| |  _ / _ \ __\___ \| | | | '_ \| __| | __| |/ _ \
| |_| |  __/ |_ ___) | |_| | |_) | |_| | |_| |  __/
 \____|\___|\__|____/ \__,_|_.__/ \__|_|\__|_|\___|

GetSubtitle — Workflow Builder

Answer a few questions to generate a command and reusable workflow.

------------------------------------------------------------------------------------------------
Commands:
    Enter  Accept default
    b      Back
    q      Quit
    Ctrl-C Cancel
------------------------------------------------------------------------------------------------
Q1. What would you like to do?

    1) Fetch      Download subtitles from a URL or title
    2) Translate  Fill missing languages with AI
    3) Modify     Clean up subtitle lines, add reading aids (furigana, hangul, pinyin, ...)
    4) Merge      Create one multi-language subtitle file
    5) Rename     Batch rename subtitle files

    Common picks:
      1-4     full workflow: download, translate, clean up, merge
      1,3,4   download + clean up + merge (no AI translation)
      5       rename titles, prefixes, change numbering
    Default: 1-4 — fetch, translate, modify, then merge.

  Numbers or ranges, or Enter for default [1-4 | q=quit] > 4
    Selected: merge.

------------------------------------------------------------------------------------------------
Q2. Folder or file to process.                                      Progress [◼◼◼◼◼◻◻◻◻◻◻◻◻] 38%

    Drop a folder of subtitle files, a single subtitle/video file,
    or any local path your selected step(s) should operate on.

  Folder or file path [b=back | q=quit] > {TMP}/Show
    Searching for: local movie folder: 1 video file(s), 0 subtitle file(s)

------------------------------------------------------------------------------------------------
Q3. Which subtitle languages do you want to collect?                Progress [◼◼◼◼◼◼◼◼◻◻◻◻◻] 62%

    List them in the order you want them displayed (top → bottom).

    Common Picks
      ja,en : Japanese on top and English below (optional furigana support)
      ko,en,es : Korean on top, then English and Spanish (optional romanization support)
      japanese,korean,english,spanish : 2-letter codes and full language names both work

  Languages (comma-separated) [ja,en | g=guide | b=back | q=quit] > ja,en

    Languages selected:
      ja → Japanese
      en → English

    Japanese furigana reading aids need the Modify step (not selected yet).
  Add Modify so I can offer Japanese furigana reading aids? [Y/n | b=back | q=quit] > n
    No reading aids this run.

------------------------------------------------------------------------------------------------
Q4. Final output format.                                            Progress [◼◼◼◼◼◼◼◼◼◼◼◻◻] 88%

    Choose the format that best matches your player.
    1) SRT  — works almost everywhere
              Plex, Jellyfin, Smart TVs, tablets, phones, VLC
    2) ASS  — best for local study playback
              Better subtitle positioning, sizing, and readability
    3) VTT  — best for browser-based language learning
              Works with a browser extension on Netflix, Disney+ & other streaming sites
    4) SMI  — Korean subtitle format
              Common in older Korean subtitle archives
    5) TXT  — plain text without timestamps

    Recommendations:
      Watching on TV, tablet, phone, Plex, or Jellyfin?
        → SRT

      Watching local video files on VLC, MPV, or desktop players?
        → ASS

      Streaming Netflix with multiple subtitles?
        → VTT (asbplayer browser plug-in required)

    Suggested default: SRT — SRT is the safest general-purpose choice.

  Final format [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Q5. Subtitle text size?                                             Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 90%

    Subtitle text size
    Format: SRT

    Please note many players ignore font sizes in SRT files.
    If your player supports sizing, these presets are recommended:

    1) Regular (16px) — recommended
    2) Smaller (12px)
    3) Larger (20px)
    4) Custom — enter exact font size

  Number [1 | b=back | q=quit] >

------------------------------------------------------------------------------------------------
Review your workflow                                                Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%

Plan
  • Use local Japanese, English files in:
    {TMP}/Show
  • Create one Japanese + English SRT study subtitle file
  • Use subtitle text size: Regular
  • Save to:
    {TMP}/Show

Smart defaults
  Display order    ja, en  (top → bottom on screen)
  Timing language  ja  (first language)
  Cleanup preset   on  (one-line subtitles + strip broadcast noise)
  Output folder    beside source

What next?
  1) Run it now
  2) Change a setting
  3) Show exact command and workflow file
  4) Save as a reusable workflow file
  5) Start over

  Number [1 | b=back | q=quit] > 1

Preflight check — 1 item(s) to know about:
  • No local subtitle files found
      Why: Optional — the run works, but may fail or look worse without it.
      Fix: Check the folder path, extract MKV subtitles, or fetch/download subtitles first.

------------------------------------------------------------------------------------------------
Running:
  getsubtitle merge {TMP}/Show --languages ja,en --format srt --font-size regular --output {TMP}/Show


======================================================================
Workflow summary
======================================================================
Completed successfully

Next steps:
  1. Merge later with: getsubtitle merge {TMP}/Show -l ja,en
  2. Re-run this workflow command after any setup fixes:
     getsubtitle merge {TMP}/Show --languages ja,en --format srt --font-size regular --output {TMP}/Show
  Open folder? [Y/n] > n
```

</details>

## Coverage gaps to add as harness scenarios

These paths are not yet golden transcripts. They are listed so UX review
does not mistake the current harness for complete product coverage.

### gap-01. No online subtitles found, manual community search suggested

- Category: `failure`
- Workflow: `fetch`
- Status: `needs_harness_transcript`
- Audit focus: `manual_search, provider_expectations, tone`

Suggested excerpt:

```text
No downloadable subtitles were found for ja, ko.
Open community search pages now? [Y/n]
```

### gap-02. MKV contains embedded subtitles after online fetch misses

- Category: `edge`
- Workflow: `fetch, translate`
- Status: `needs_harness_transcript`
- Audit focus: `mkv_extraction, recovery, local_files`

Suggested excerpt:

```text
Online fetch did not find subtitles, but this MKV contains subtitle tracks.
Extract them and continue? [Y/n]
```
