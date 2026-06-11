# GetSubtitle — UX Philosophy

The **why** behind the product. [`AGENTS.md`](../../AGENTS.md) is the **what** (the rules);
this file explains the reasoning so you can apply the rules to situations
they don't literally cover. Read [`AGENTS.md`](../../AGENTS.md) first. When this file and
AGENTS.md seem to overlap, AGENTS.md owns the rule — this file owns the
rationale.

## What the product actually is

GetSubtitle is a **language-learning workflow tool**, not a subtitle
downloader. Downloading is step one; the value is in turning raw tracks
into something you can study from. Every design call should ask "does this
help someone *learn* from the subtitles," not just "did we fetch a file."

## Who we optimize for, and why

- **Language learners** (e.g. English speaker → Japanese, anime fans) are the
  primary audience. Most UX tradeoffs resolve in their favor.
- **Plex / local-media users** matter because study often happens on a TV or
  tablet — which is *why* compatibility and format choice are first-class, not
  an afterthought.
- **CLI power users** already have full control. That's *why* the wizard can be
  beginner-first without dumbing anything down: experts skip it. Never remove
  advanced functionality to make the wizard simpler — the two audiences are
  served by two surfaces, not one watered-down one.

## Why human subtitles come first

AI translation drifts, mistimes, and flattens nuance — and a learner
can't tell a mistranslation from the truth, so AI-translation errors teach the
*wrong* thing. Human subtitles are the trustworthy baseline; AI translation
only fills gaps the learner would otherwise have nothing for. Designing around
AI-translation-as-primary would quietly degrade the one thing learners depend
on: accuracy.

## Why examples beat explanations

A beginner reading "adds furigana readings" cannot picture the result. Shown
`勉強する → べんきょうする`, they understand instantly *and* retain it. For a
learning tool, the example **is** the explanation — abstractions make the user
do translation work the product should have done for them.

## Why outcomes come before implementation

Users measure success by what they got ("Downloaded: 2 files"), not by our
internal bookkeeping ("planned 2, wrote 2"). Implementation-flavored output
makes a working tool feel like a debugger and quietly shifts cognitive load
onto the user. Save the internals for `--debug`-style requests.

## Why progressive disclosure

Cognitive load is the enemy of onboarding. A user who just hit a failure
needs, in order: *what happened*, then *what to do*, and only if they ask,
*the technical detail*. Dumping all three at once buries the recovery action
— the one thing they actually need — under noise.

## Why the wizard is beginner-first

The CLI already exists for experts, so the wizard's real job isn't input
collection — it's **teaching**. It should explain decisions, recommend sane
defaults, and introduce concepts gradually, so that a wizard user gradually
becomes a CLI user.

## Why the vocabulary is shared and fixed

The wizard deliberately uses the same five verbs as the CLI —
**Fetch / Translate / Modify / Merge / Rename** — so that learning the wizard
*is* learning the CLI. Renaming them in the wizard ("Download", "Combine")
would create two vocabularies for one mental model, and the bridge from
beginner to power user would break. That's why these names are non-negotiable.

## Why no format is universally best

SRT, ASS, and VTT each win in a different ecosystem — broad device
compatibility, desktop/local study layout, and browser study respectively.
A single blanket recommendation (e.g. "always VTT") would mislead most users,
because the right answer depends on *where they watch*. So we show the real
format names with compatibility guidance and let the situation decide.

## Why failures must differ

"No subtitles exist," "the subtitle source timed out," "you're rate-limited," and
"the title didn't match" need *different* recovery actions — search an
alternate title, retry now, wait a few minutes, try a different title source.
Collapsing them into one generic error strands the user with no usable next
step, which is worse than a slightly longer message.

## Priority order when principles conflict

When two of these pull in different directions, resolve in this order:

1. **Subtitle accuracy** — wrong subtitles teach wrong things.
2. **User trust** — never surprise the user or do something they didn't ask for.
3. **Beginner-friendly UX** — clarity and onboarding.
4. **Human subtitles over machine translation.**
5. **Compatibility across players.**

## When in doubt

Prefer **short, clear, example-driven, actionable** over **technical, verbose,
implementation-focused**. The product should feel like a patient guide, not a
console.
