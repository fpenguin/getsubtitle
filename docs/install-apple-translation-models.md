# Install Apple Translation Models

GetSubtitle can use Apple's on-device Translation framework through the
open-source `translate` CLI. The CLI is installed with Homebrew, but the
language models themselves live in macOS System Settings.

Use this when you choose:

```text
--engine apple
```

## Requirements

- Apple Silicon Mac
- macOS 26/Tahoe or newer
- Apple Translation language models downloaded for the pairs you need

## Install the CLI

```bash
brew install Arthur-Ficial/tap/translate
translate --version
```

## Download Language Models

Open System Settings:

```bash
open "x-apple.systempreferences:com.apple.Localization-Settings.extension"
```

Then:

1. Go to **General > Language & Region**.
2. Scroll down and open **Translation Languages**.
3. Download the languages you need.
4. Turn on **On-Device Mode**.
5. Wait for the downloads to finish, then click **Done**.

For example, Japanese to Korean needs the `ja-ko` pair. English to Spanish
needs `en-es`.

## Verify

Run:

```bash
translate --installed
```

You should see one line per installed pair, such as:

```text
en-es
ja-ko
```

Then test a sentence:

```bash
echo "I thought you were coming back tomorrow." | translate --from en --to es --no-install --quiet
```

## Use With GetSubtitle

```bash
getsubtitle translate PATH -l ja,ko --engine apple
```

The interactive wizard checks `translate --installed` before running. If a
pair is missing, it will tell you which one to install.

## Troubleshooting

**`translate` command not found**

Install the CLI:

```bash
brew install Arthur-Ficial/tap/translate
```

**`translate --installed` prints nothing**

The language downloads have not finished, or On-Device Mode is off. Reopen
System Settings > General > Language & Region > Translation Languages.

**`model for ja-ko is not installed`**

Download the missing language pair in Translation Languages, then verify with:

```bash
translate --installed
```

**`Error: Unable to Translate`**

The CLI can see Apple's Translation framework, but macOS cannot translate with
the requested pair yet. Recheck that the pair is downloaded and On-Device Mode
is enabled.

Note: upstream `translate --install` may not reliably trigger downloads from a
headless CLI on current Tahoe builds, so System Settings is the safer setup
path.
