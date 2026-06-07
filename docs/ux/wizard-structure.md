# Wizard structure

Generated from the current interactive wizard and scenario harness.
Question numbers are intentionally dynamic: the wizard skips irrelevant
questions based on Q1, source type, local coverage, selected languages,
reading aids, and output format.

## Global commands

- `Enter` accepts the displayed default.
- `b` goes back one logical question.
- `q` quits and saves a recoverable draft only after enough answers exist.
- `Ctrl-C` cancels immediately.

## High-level flow

```text
Start
  -> Q1 choose workflow steps: Fetch / Translate / Modify / Merge / Rename
  -> If Rename only: rename source -> variation picker -> change planner -> preview -> apply/copy
  -> Otherwise:
       source selection
       languages
       fetch scope when Fetch is selected
       translation engine when Translate is selected
       reading aids when Modify is selected and language supports them
       output format when Merge or converted reading-aid output needs it
       subtitle text size when selected format supports useful size control
       output folder
       plan preview
       final action: Run / Save / Edit / Restart / Quit / Show exact command
       preflight: blockers + warnings + info
       run summary or saved-workflow instructions
```

## Step branches

| Branch | Main questions | Skips |
|---|---|---|
| Fetch | source type, URL/title/path, season/episode scope | local modify-only questions that do not apply |
| Translate | languages, engine, dependency preflight | engine question when user skips translation |
| Modify | local source, languages, reading aids, cleanup defaults | reading-aid menu when selected languages do not support it |
| Merge | language order, master timing, format, size, output | merge questions for single-language output |
| Rename | folder/file, filename variation, fields to change, apply/copy | fetch/translate/modify/merge questions |

## UX audit checkpoints

- **Inconsistent wording:** compare “workflow”, “command”, “TOML”, “multi-language subtitle”, “merge”, and “reading aid”.
- **Bad defaults:** Q1 default, translation default, format default, output folder default, copy-vs-original rename default.
- **Duplicated questions:** source path, languages, output path, format, and text size should appear once per logical flow.
- **Missing explanations:** provider failures, local coverage gaps, embedded MKV subtitles, VTT/ASS/SRT limitations.
- **Terminology issues:** prefer beginner terms first, then technical terms in parentheses.
