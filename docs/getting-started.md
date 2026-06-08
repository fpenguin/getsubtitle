# Getting Started

GetSubtitle has two beginner-friendly entry points:

```sh
getsubtitle setup
getsubtitle -i
```

`setup` is optional first-time onboarding. It asks what you watch, what
languages you already understand, what languages you are learning, where you
watch, and whether you want machine translation when subtitles are missing.

It then recommends useful providers and reading-aid extras, saves a profile,
and lets the interactive wizard pre-fill common answers.

`-i` is the guided workflow builder. It asks what you want to do, where the
subtitles should come from, which languages you want, whether to add reading
aids, and where to save the result.

The wizard can:

- run the workflow immediately;
- save a reusable TOML workflow;
- show the exact command it generated;
- let you edit one answer without starting over;
- probe missing dependencies or API keys before running.

## How It Works

1. **Fetch** - download subtitles from a streaming/catalog URL, scan a local
   folder, or both.
2. **Modify** - clean broadcast noise, add reading aids, convert legacy `.smi`,
   or extract text subtitles from local files.
3. **Merge** - stack 2-4 language tracks into one synced study file.

The wizard runs the common path by default, but each step can also be used on
its own from the CLI.

## First Workflow

```sh
getsubtitle -i
```

Choose a URL, title, folder, or file; choose your languages; then let the wizard
build the command. At the end you can run, save, edit, restart, quit, or show the
exact command.
