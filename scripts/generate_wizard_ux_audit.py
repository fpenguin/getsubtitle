#!/usr/bin/env python3
"""Generate UX-audit artifacts for the interactive wizard.

The wizard transcript harness is the source of truth for tested flows.
This script collects those blessed transcripts into three audit files:

1. docs/ux/wizard-structure.md
2. docs/ux/wizard-representative-transcripts.md
3. docs/ux/wizard-ux-metadata.json

The JSON metadata intentionally calls out copywriting risks so reviewers
can audit wording without reverse-engineering the wizard code.
"""

from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT_DIR = ROOT / "tests" / "wizard_transcripts"
OUT_DIR = ROOT / "docs" / "ux"


PATHS: list[dict[str, object]] = [
    {
        "id": "path-01",
        "scenario": "persona_enter_spammer",
        "name": "Default full workflow, Enter-heavy happy path",
        "workflow": ["fetch", "translate", "modify", "merge"],
        "category": "happy",
        "user_intent": "Accept defaults and run a complete subtitle workflow.",
        "audit_focus": ["defaults", "progress", "final_action"],
        "notes": "Shows whether defaults feel safe when the user keeps pressing Enter.",
    },
    {
        "id": "path-02",
        "scenario": "persona_plex_mash",
        "name": "Local Plex folder with missing languages, then fetch",
        "workflow": ["fetch", "modify", "merge"],
        "category": "common",
        "user_intent": "Work from a local folder and search online for missing subtitles.",
        "audit_focus": ["missing_explanation", "manual_search", "source_reuse"],
        "notes": "Important for users who start from Plex folders instead of catalog URLs.",
    },
    {
        "id": "path-03",
        "scenario": "persona_furigana_newbie",
        "name": "Japanese learner adds hiragana reading aid",
        "workflow": ["modify", "merge"],
        "category": "happy",
        "user_intent": "Turn Japanese + English subtitles into a learner-friendly file.",
        "audit_focus": ["terminology", "reading_aids", "format_default"],
        "notes": "Primary beginner copy path for furigana/reading-aid explanation.",
    },
    {
        "id": "path-04",
        "scenario": "persona_korean_learner",
        "name": "Korean learner adds Revised Romanization",
        "workflow": ["modify", "merge"],
        "category": "happy",
        "user_intent": "Stack Korean and English with Korean romanization.",
        "audit_focus": ["language_specific_copy", "reading_aids", "format_default"],
        "notes": "Ensures the wizard is not Japanese-only in tone or examples.",
    },
    {
        "id": "path-05",
        "scenario": "persona_merge_only_folder",
        "name": "Merge-only local folder",
        "workflow": ["merge"],
        "category": "common",
        "user_intent": "Combine existing subtitles without fetching or modifying.",
        "audit_focus": ["skipped_questions", "defaults", "output_explanation"],
        "notes": "A common power-user workflow that should stay short.",
    },
    {
        "id": "path-06",
        "scenario": "persona_modify_only_single_file",
        "name": "Modify-only single subtitle file",
        "workflow": ["modify"],
        "category": "common",
        "user_intent": "Clean or add reading aids to one subtitle file.",
        "audit_focus": ["single_file_scope", "format_choice", "font_size"],
        "notes": "Checks that single-file input does not imply a whole season.",
    },
    {
        "id": "path-07",
        "scenario": "persona_rename_episodes",
        "name": "Rename-only episode range",
        "workflow": ["rename"],
        "category": "common",
        "user_intent": "Batch rename subtitle filenames while keeping originals safe.",
        "audit_focus": ["safety_default", "preview", "confirmation"],
        "notes": "Rename is destructive-adjacent; copywriting must make copy vs original obvious.",
    },
    {
        "id": "path-08",
        "scenario": "persona_no_key_deepl",
        "name": "DeepL selected without API key",
        "workflow": ["translate", "modify", "merge"],
        "category": "failure",
        "user_intent": "Use DeepL before setup is complete.",
        "audit_focus": ["setup_blocker", "save_for_later", "preflight"],
        "notes": "Failure should feel recoverable, not like a crash.",
    },
    {
        "id": "path-09",
        "scenario": "persona_ollama_down",
        "name": "Ollama selected but daemon/model unavailable",
        "workflow": ["translate", "modify", "merge"],
        "category": "failure",
        "user_intent": "Use local AI translation before Ollama is ready.",
        "audit_focus": ["setup_blocker", "local_dependency", "save_for_later"],
        "notes": "Good test for plain-English dependency copy.",
    },
    {
        "id": "path-10",
        "scenario": "persona_wrong_lang",
        "name": "Requested language missing from local folder",
        "workflow": ["modify", "merge"],
        "category": "edge",
        "user_intent": "Merge languages that are not actually present locally.",
        "audit_focus": ["missing_explanation", "manual_search", "recovery"],
        "notes": "Should teach the user what the folder contains and what to try next.",
    },
    {
        "id": "path-11",
        "scenario": "trap_skip_mt_no_scold",
        "name": "Skip AI translation intentionally",
        "workflow": ["fetch", "modify", "merge"],
        "category": "edge",
        "user_intent": "Accept gaps instead of translating.",
        "audit_focus": ["tone", "warnings", "no_scolding"],
        "notes": "Skipping MT is a valid choice; warnings should not sound like errors.",
    },
    {
        "id": "path-12",
        "scenario": "trap_crunchyroll_auto_scope_requires_range",
        "name": "Crunchyroll season page with absolute episode numbers",
        "workflow": ["fetch", "modify", "merge"],
        "category": "edge",
        "user_intent": "Fetch a whole visible Crunchyroll season that starts at E25.",
        "audit_focus": ["episode_scope", "numbering", "examples"],
        "notes": "Most important scope copy for anime streaming pages.",
    },
    {
        "id": "path-13",
        "scenario": "trap_local_file_scopes_to_episode",
        "name": "Local video file should scope to one episode",
        "workflow": ["fetch", "modify", "merge"],
        "category": "edge",
        "user_intent": "Operate on one selected episode file only.",
        "audit_focus": ["single_file_scope", "surprise_prevention"],
        "notes": "Regression guard against accidentally scanning a whole season.",
    },
    {
        "id": "path-14",
        "scenario": "trap_open_folder_only_opens",
        "name": "Open folder after run",
        "workflow": ["modify", "merge"],
        "category": "edge",
        "user_intent": "Open the result folder without re-running post steps.",
        "audit_focus": ["post_run_action", "side_effects"],
        "notes": "Protects against the old double-dispatch bug.",
    },
    {
        "id": "path-15",
        "scenario": "persona_drag_quoted",
        "name": "Finder drag-drop quoted path",
        "workflow": ["modify", "merge"],
        "category": "common",
        "user_intent": "Paste a quoted path from Finder/Terminal.",
        "audit_focus": ["path_validation", "beginner_input"],
        "notes": "Mac users commonly paste paths wrapped in quotes.",
    },
    {
        "id": "path-16",
        "scenario": "trap_quoted_path_stripped",
        "name": "Quoted path stripped before validation",
        "workflow": ["modify", "merge"],
        "category": "edge",
        "user_intent": "Use a path with shell-style quotes.",
        "audit_focus": ["path_validation", "error_prevention"],
        "notes": "A tighter regression trap for quoted path handling.",
    },
    {
        "id": "path-17",
        "scenario": "persona_title_typo_at_q1",
        "name": "Free text entered at Q1 instead of choosing a mode",
        "workflow": ["fetch", "modify", "merge"],
        "category": "failure",
        "user_intent": "Type a title into the first selection prompt.",
        "audit_focus": ["invalid_selection", "recovery", "plain_language"],
        "notes": "Checks that the error explains how to search by title.",
    },
    {
        "id": "path-18",
        "scenario": "trap_q1_rejects_free_text",
        "name": "Q1 rejects free text and recovers",
        "workflow": ["fetch", "modify", "merge"],
        "category": "failure",
        "user_intent": "Recover after entering non-menu text.",
        "audit_focus": ["invalid_selection", "default_safety"],
        "notes": "Similar to path 17 but covers the trap path explicitly.",
    },
    {
        "id": "path-19",
        "scenario": "persona_back_navigation",
        "name": "Back navigation through a previous step",
        "workflow": ["modify", "merge"],
        "category": "edge",
        "user_intent": "Correct a previous answer without restarting.",
        "audit_focus": ["back_navigation", "state_reset"],
        "notes": "Back should move one logical question, not lose unrelated answers.",
    },
    {
        "id": "path-20",
        "scenario": "persona_restart_decline",
        "name": "Start-over selected but user declines discard",
        "workflow": ["modify", "merge"],
        "category": "edge",
        "user_intent": "Avoid losing answers after picking restart by mistake.",
        "audit_focus": ["destructive_confirmation", "draft_safety"],
        "notes": "Restart is a destructive workflow action and needs confirmation.",
    },
    {
        "id": "path-21",
        "scenario": "persona_power_edit",
        "name": "Change a setting from final screen",
        "workflow": ["modify"],
        "category": "edge",
        "user_intent": "Change one answer after reviewing the plan.",
        "audit_focus": ["edit_flow", "state_reset", "numbering"],
        "notes": "Covers the final-action edit branch.",
    },
    {
        "id": "path-22",
        "scenario": "persona_re_runner",
        "name": "Save reusable TOML, then override later",
        "workflow": ["fetch", "modify", "merge"],
        "category": "common",
        "user_intent": "Create a reusable workflow for future runs.",
        "audit_focus": ["toml_reuse", "override_explanation"],
        "notes": "Important copy for non-programmers learning what a workflow file does.",
    },
    {
        "id": "path-23",
        "scenario": "trap_toml_save_reuse_hint",
        "name": "TOML save includes override hint and open-folder prompt",
        "workflow": ["modify", "merge"],
        "category": "edge",
        "user_intent": "Save a workflow and understand how CLI overrides work.",
        "audit_focus": ["toml_reuse", "open_folder", "examples"],
        "notes": "Pins the post-save educational copy.",
    },
    {
        "id": "path-24",
        "scenario": "persona_url_first",
        "name": "URL-first fetch workflow",
        "workflow": ["fetch", "modify", "merge"],
        "category": "common",
        "user_intent": "Start from an IMDb/catalog URL.",
        "audit_focus": ["source_type", "scope", "provider_expectations"],
        "notes": "Common path for users who do not have local subtitle files yet.",
    },
    {
        "id": "path-25",
        "scenario": "trap_engine_mapping_deepl_emits_deepl",
        "name": "DeepL engine maps correctly in CLI/TOML",
        "workflow": ["fetch", "translate", "modify", "merge"],
        "category": "edge",
        "user_intent": "Save a DeepL translation workflow.",
        "audit_focus": ["terminology", "engine_mapping"],
        "notes": "Protects against Argos/DeepL wording and emission mixups.",
    },
    {
        "id": "path-26",
        "scenario": "trap_enter_accepts_default",
        "name": "Enter accepts defaults at yes/no and menu prompts",
        "workflow": ["fetch", "translate", "modify", "merge"],
        "category": "edge",
        "user_intent": "Move quickly through defaults.",
        "audit_focus": ["default_prompt", "enter_behavior"],
        "notes": "Important for confidence: displayed defaults must actually work.",
    },
    {
        "id": "path-27",
        "scenario": "trap_format_default_vtt_for_ja_hiragana",
        "name": "Japanese hiragana reading aid defaults to VTT",
        "workflow": ["modify", "merge"],
        "category": "edge",
        "user_intent": "Use true Japanese ruby output.",
        "audit_focus": ["format_default", "player_limitations"],
        "notes": "Needs careful copy because VTT ruby is great in asbplayer but uneven elsewhere.",
    },
    {
        "id": "path-28",
        "scenario": "trap_modify_merge_no_fetch_uses_positional_path",
        "name": "Modify+merge local path emits positional CLI correctly",
        "workflow": ["modify", "merge"],
        "category": "edge",
        "user_intent": "Use local files without fetch.",
        "audit_focus": ["cli_equivalence", "source_override"],
        "notes": "Prevents confusing generated commands.",
    },
    {
        "id": "path-29",
        "scenario": "persona_folder_movie",
        "name": "Movie folder workflow",
        "workflow": ["fetch", "modify", "merge"],
        "category": "common",
        "user_intent": "Process a movie-style folder rather than a TV season.",
        "audit_focus": ["movie_scope", "episode_labels"],
        "notes": "Checks movie-shaped filenames and S00E00 behavior.",
    },
    {
        "id": "path-30",
        "scenario": "trap_existing_merge_output_preflight",
        "name": "Existing merged output detected before run",
        "workflow": ["modify", "merge"],
        "category": "failure",
        "user_intent": "Run a merge where the target file already exists.",
        "audit_focus": ["overwrite_safety", "preflight", "plain_language"],
        "notes": "Warns before dispatch so the user understands why merge may skip writing.",
    },
    {
        "id": "path-31",
        "scenario": "trap_partial_local_coverage_preflight",
        "name": "Partial local subtitle coverage detected before run",
        "workflow": ["modify", "merge"],
        "category": "edge",
        "user_intent": "Merge a folder where some episodes lack one requested language.",
        "audit_focus": ["partial_coverage", "missing_explanation", "preflight"],
        "notes": "Shows missing episode/language examples before the command runs.",
    },
    {
        "id": "path-32",
        "scenario": "trap_no_local_subtitles_preflight",
        "name": "No local subtitles found before run",
        "workflow": ["merge"],
        "category": "failure",
        "user_intent": "Run a local merge on a folder that only contains video files.",
        "audit_focus": ["no_subtitles", "mkv_extraction", "recovery"],
        "notes": "Explains that the folder has no subtitle files and hints at extraction/fetch.",
    },
]


GAP_PATHS: list[dict[str, object]] = [
    {
        "id": "gap-01",
        "name": "No online subtitles found, manual community search suggested",
        "workflow": ["fetch"],
        "category": "failure",
        "status": "needs_harness_transcript",
        "audit_focus": ["manual_search", "provider_expectations", "tone"],
        "suggested_excerpt": "No downloadable subtitles were found for ja, ko.\nOpen community search pages now? [Y/n]",
    },
    {
        "id": "gap-02",
        "name": "MKV contains embedded subtitles after online fetch misses",
        "workflow": ["fetch", "translate"],
        "category": "edge",
        "status": "needs_harness_transcript",
        "audit_focus": ["mkv_extraction", "recovery", "local_files"],
        "suggested_excerpt": "Online fetch did not find subtitles, but this MKV contains subtitle tracks.\nExtract them and continue? [Y/n]",
    },
]


def _question_map() -> str:
    return dedent(
        """\
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
               fetch scope when Fetch is selected
               languages
               translation engine when Translate is selected
               reading aids when Modify is selected and language supports them
               output format when Merge or converted reading-aid output needs it
               subtitle text size when selected format supports useful size control
               output folder
               review workflow
               final action: Run / Change a setting / Show exact command / Save / Start over / Quit
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
        """
    )


def _load_transcript(scenario: str) -> str:
    path = TRANSCRIPT_DIR / f"{scenario}.txt"
    if not path.exists():
        raise FileNotFoundError(f"missing transcript for {scenario}: {path}")
    return path.read_text(encoding="utf-8")


def _transcripts_markdown() -> str:
    lines = [
        "# Representative wizard transcripts",
        "",
        "These are harness-backed transcripts from `tests/wizard_transcripts/`.",
        "Use them to audit copywriting, defaults, prompt ordering, and failure recovery.",
        "",
        "## Tested paths",
        "",
    ]
    for item in PATHS:
        scenario = str(item["scenario"])
        transcript = _load_transcript(scenario).rstrip()
        title = f'{item["id"]}. {item["name"]}'
        lines.extend([
            f"### {title}",
            "",
            f"- Category: `{item['category']}`",
            f"- Workflow: `{', '.join(item['workflow'])}`",
            f"- Scenario: `tests/wizard_scenarios/{scenario}.py`",
            f"- Audit focus: `{', '.join(item['audit_focus'])}`",
            f"- Notes: {item['notes']}",
            "",
            "<details>",
            f"<summary>Show transcript ({scenario})</summary>",
            "",
            "```text",
            transcript,
            "```",
            "",
            "</details>",
            "",
        ])

    lines.extend([
        "## Coverage gaps to add as harness scenarios",
        "",
        "These paths are not yet golden transcripts. They are listed so UX review",
        "does not mistake the current harness for complete product coverage.",
        "",
    ])
    for item in GAP_PATHS:
        lines.extend([
            f"### {item['id']}. {item['name']}",
            "",
            f"- Category: `{item['category']}`",
            f"- Workflow: `{', '.join(item['workflow'])}`",
            f"- Status: `{item['status']}`",
            f"- Audit focus: `{', '.join(item['audit_focus'])}`",
            "",
            "Suggested excerpt:",
            "",
            "```text",
            str(item["suggested_excerpt"]),
            "```",
            "",
        ])
    return "\n".join(lines)


def _metadata() -> dict[str, object]:
    category_counts: dict[str, int] = {}
    workflow_counts: dict[str, int] = {}
    for item in PATHS:
        category = str(item["category"])
        category_counts[category] = category_counts.get(category, 0) + 1
        workflow_key = "+".join(str(s) for s in item["workflow"])
        workflow_counts[workflow_key] = workflow_counts.get(workflow_key, 0) + 1

    return {
        "schema_version": 1,
        "source": {
            "wizard_code": "getsubtitle_core.py",
            "scenario_dir": "tests/wizard_scenarios",
            "transcript_dir": "tests/wizard_transcripts",
        },
        "summary": {
            "tested_path_count": len(PATHS),
            "gap_path_count": len(GAP_PATHS),
            "category_counts": category_counts,
            "workflow_counts": workflow_counts,
        },
        "audit_dimensions": [
            "inconsistent wording",
            "bad defaults",
            "duplicated questions",
            "missing explanations",
            "terminology issues",
            "unsafe or surprising side effects",
        ],
        "paths": PATHS,
        "coverage_gaps": GAP_PATHS,
    }


def _outputs() -> dict[Path, str]:
    return {
        OUT_DIR / "wizard-structure.md": _question_map(),
        OUT_DIR / "wizard-representative-transcripts.md": _transcripts_markdown(),
        OUT_DIR / "wizard-ux-metadata.json": json.dumps(_metadata(), ensure_ascii=False, indent=2) + "\n",
    }


def _check_outputs(outputs: dict[Path, str]) -> bool:
    ok = True
    for path, expected in outputs.items():
        if not path.exists():
            print(f"missing generated artifact: {path.relative_to(ROOT)}")
            ok = False
            continue
        current = path.read_text(encoding="utf-8")
        if current != expected:
            print(f"stale generated artifact: {path.relative_to(ROOT)}")
            diff = difflib.unified_diff(
                current.splitlines(),
                expected.splitlines(),
                fromfile=str(path.relative_to(ROOT)),
                tofile=str(path.relative_to(ROOT)) + " (expected)",
                lineterm="",
            )
            for idx, line in enumerate(diff):
                if idx >= 80:
                    print("... diff truncated; rerun without --check to regenerate")
                    break
                print(line)
            ok = False
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate UX-audit artifacts for the interactive wizard.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify generated UX audit artifacts are current without rewriting files.",
    )
    args = parser.parse_args(argv)
    outputs = _outputs()
    if args.check:
        return 0 if _check_outputs(outputs) else 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
    print(f"Wrote UX audit artifacts to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
