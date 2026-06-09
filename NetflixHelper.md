# Netflix Helper design spec

Netflix Helper is a companion idea for GetSubtitle. Its job is to make
Netflix and Crunchyroll pages useful as metadata and workflow starters for language
learners, without turning GetSubtitle into a subtitle scraper.

## Goal

Help a learner go from a Netflix and Crunchyroll movie/show page to a useful GetSubtitle
workflow:

1. Identify the title, Netflix work ID, season, episode, and available
   episode list.
2. Build better subtitle-search terms and external metadata IDs.
3. Create a GetSubtitle command or workflow file.
4. Search supported external subtitle sources and open manual search pages.
5. Produce player-ready files for asbplayer, local video players, Plex,
   Jellyfin, phones, tablets, or TVs.

The helper should support multiple requested subtitle languages and, for
shows, multiple episodes in one batch.

## Non-goals

Netflix Helper must not:

- Bypass DRM, region locks, login walls, ads, or account restrictions.
- Capture or export protected media streams.
- Steal cookies, tokens, account identifiers, or playback secrets.
- Promise direct download of official platform caption files.
- Automate behavior that requires defeating platform access controls.

If a browser-visible page exposes safe metadata, the helper may use that
metadata. If a user independently has subtitle files, GetSubtitle can process
them. Direct logged-in caption extraction is out of scope unless a future
legal/terms review explicitly approves a narrow user-controlled export path.

## Product shape

Netflix Helper should be useful in two forms:

1. **Chrome extension**
   - Best UX for non-technical users.
   - Reads the current Netflix page context.
   - Shows title/episode/language options.
   - Exports a GetSubtitle workflow or sends it to a local helper.

2. **Standalone helper**
   - Works without a browser extension.
   - Opens a browser where user can login with their credentials
   - Accepts a Netflix URL or exported manifest JSON.
   - Generates a GetSubtitle command/TOML.
   - Can run GetSubtitle if installed.

The Chrome extension should be optional. GetSubtitle itself should still work
with Netflix URLs through the existing Netflix ID to metadata bridge.

## Safe data model

The helper should pass only safe metadata to GetSubtitle:

```json
{
  "source": "netflix",
  "url": "https://www.netflix.com/watch/...",
  "netflix_id": "81234567",
  "title": "Example Show",
  "season": "1",
  "episodes": [
    {
      "season": "1",
      "episode": "1",
      "absolute_episode": "1",
      "title": "Episode One",
      "url": "https://www.netflix.com/watch/..."
    }
  ],
  "requested_languages": ["ja", "en", "ko"],
  "preferred_output": {
    "format": "vtt",
    "reading": ["ja:hiragana"],
    "merge": true
  }
}
```

Do not include cookies, bearer tokens, license URLs, media URLs, account IDs,
or protected caption URLs in the manifest.

## Chrome extension UX

### Page button

On Netflix title/watch pages, show a small extension popup:

```text
Netflix Helper

Detected:
  Example Show
  Season 1

What do you want?
  1) Current episode
  2) Selected episode range
  3) Whole season

Subtitle languages:
  ja,en,ko

Output:
  VTT for browser/asbplayer
  SRT for maximum compatibility
  Others

Next:
  1) Copy GetSubtitle command
  2) Save workflow file
  3) Send to local GetSubtitle
  4) Open external subtitle searches
```

### Multi-episode flow

For TV shows:

```text
Episodes
  1) Current episode only
  2) Episodes 1-3
  3) Whole visible season
  4) Custom range

Episode range [all] >
```

The helper should prefer season-relative numbering for GetSubtitle. If
Netflix shows absolute episode numbers, include both absolute and
season-relative numbers in the manifest.

### Multi-language flow

Allow multiple languages in one request:

```text
Languages to collect:
  ja,en,ko

Reading aids:
  ja:hiragana

Create:
  One multi-language file per episode
```

The extension should warn if the user selects four or more languages:

```text
Most people find 2-3 languages easiest to read.
4+ languages can crowd smaller screens.
```

## GetSubtitle integration

### Option A: Generate a command

The helper can copy a command:

```bash
getsubtitle "https://www.netflix.com/watch/81234567" \
  --season 1 --episode 1-12 \
  --languages ja,en,ko \
  --modify --strip-cc-noise --single-line --reading ja:hiragana \
  --merge --format vtt \
  --output ~/Downloads/GetSubtitle
```

### Option B: Generate TOML

The helper can save a workflow file:

```toml
[fetch]
source = "https://www.netflix.com/watch/81234567"
season = "1"
episode = "1-12"
languages = "ja,en,ko"

[modify]
single_line = true
strip_cc_noise = true
reading = "ja:hiragana"

[merge]
format = "vtt"

[output]
target = "~/Downloads/GetSubtitle"
```

### Option C: Native Messaging

Chrome extension sends the manifest to a local native host:

```text
Chrome extension
  -> Native Messaging host
    -> getsubtitle run generated-workflow.toml
```

This gives the smoothest UX but needs installer support.

### Option D: Localhost bridge

GetSubtitle can run a local helper server:

```bash
getsubtitle helper netflix --listen
```

The extension posts the manifest to localhost. This is easier to debug than
Native Messaging but needs clear security rules:

- Bind only to `127.0.0.1`.
- Require a one-time pairing token.
- Reject requests from non-extension origins.
- Never accept cookies or Netflix auth data.

## Standalone helper CLI

Possible command:

```bash
getsubtitle netflix-helper "https://www.netflix.com/watch/81234567" \
  --languages ja,en,ko \
  --season 1 \
  --episode all \
  --reading ja:hiragana \
  --format vtt \
  --save netflix-workflow.toml
```

Alternative external package:

```bash
netflix-helper export "https://www.netflix.com/watch/81234567" \
  --output manifest.json

getsubtitle --manifest manifest.json
```

Recommendation: keep the first implementation inside GetSubtitle as a
metadata/workflow helper. Split into a separate extension repo only when the
browser UI is ready.

## Subtitle acquisition strategy

Netflix Helper should not assume Netflix is the subtitle source.

Preferred order:

1. Use Netflix URL/ID to identify title and episode metadata.
2. Bridge to Wikidata, IMDb, TMDB, TVDB when possible.
3. Search supported external subtitle providers with confidence checks.
4. Use alternate titles and localized titles.
5. If automatic search misses, open targeted community search pages.
6. If subtitles are found manually, let GetSubtitle convert/clean/merge them.
7. If a base language is available, optionally machine-translate missing
   languages with DeepL, Ollama, or Argos.

For language learners, the ideal batch output is:

```text
Example Show - S01E01.ja-en-ko.vtt
Example Show - S01E02.ja-en-ko.vtt
Example Show - S01E03.ja-en-ko.vtt
...
```

## Batch behavior

For multiple episodes, build a job matrix:

```text
episodes × requested languages
```

Example:

```text
Episodes: 12
Languages: ja,en,ko
Search jobs: 36
Output files: 12 merged files
```

Rules:

- Cache metadata per Netflix ID.
- Cache provider search results per title/language/episode.
- Limit external provider concurrency to avoid rate limits.
- Prefer provider confidence over speed.
- Show a compact summary before download:

```text
Subtitle plan
  Show: Example Show
  Episodes: S01E01-S01E12
  Languages: Japanese, English, Korean
  Output: one VTT per episode

Confidence
  English: likely
  Japanese: may need manual search
  Korean: may need manual search
```

## File naming

Use GetSubtitle's existing naming rules:

```text
{Title} - S{season}E{episode}.{language-stack}.{format}
```

Examples:

```text
Example Show - S01E01.ja-en-ko.vtt
Example Show - S01E01.ja.hiragana.vtt
Example Show - S01E01.en.srt
```

If Netflix uses absolute numbering, preserve both concepts in metadata but
write season-relative filenames by default:

```text
Netflix shows: E25-E37
Output files: S03E01-S03E13
```

Offer an advanced option for absolute display numbering if users need it.

## Viewing workflows

### Browser/asbplayer

Best for:

- Netflix in browser
- multiple subtitle tracks
- Japanese ruby VTT

Output:

```text
VTT
```

### Local desktop player

Best for:

- downloaded/local videos
- font size control
- stable stacked layout

Output:

```text
ASS
```

### TV/tablet/Plex/Jellyfin

Best for:

- compatibility
- simple dual subtitles

Output:

```text
SRT
```

## Extension permissions

Minimal Chrome permissions:

```json
{
  "permissions": ["activeTab", "storage"],
  "host_permissions": ["https://www.netflix.com/*"],
  "optional_permissions": ["nativeMessaging", "downloads"]
}
```

Avoid broad host permissions. Do not request webRequest access unless a later
approved design has a clear reason.

## Privacy and security

- Store preferences locally.
- Do not log account identifiers.
- Do not persist browsing history beyond explicit saved workflows.
- Do not transmit page data to a remote service.
- Native helper must be opt-in and local-only.
- Every generated workflow should be visible before running.

## Failure UX

When automatic search fails:

```text
Could not find subtitles automatically

Show:
  Example Show
Requested:
  Japanese, English, Korean
Result:
  Japanese: 0 / 12 episodes
  English:  12 / 12 episodes
  Korean:   0 / 12 episodes

What you can do:
  1. Open subtitle search pages.
  2. Try alternate title searches.
  3. Translate missing languages from English.
```

Do not dump provider diagnostics by default. Offer:

```text
Show technical details? [y/N]
```

## Milestones

### Phase 1: GetSubtitle-only metadata helper

- Improve Netflix URL parsing.
- Bridge Netflix ID to IMDb/TMDB/TVDB through Wikidata.
- Generate better title aliases.
- Add `getsubtitle --help netflix` or `getsubtitle --help streaming`.
- Produce command/TOML examples for Netflix/asbplayer.

### Phase 2: Manifest workflow

- Define `manifest.json`.
- Add `getsubtitle --manifest manifest.json`.
- Support batch episodes/languages.
- Show preflight summary before provider search.

### Phase 3: Chrome extension prototype

- Detect Netflix title/watch pages.
- Extract safe metadata.
- Generate manifest JSON.
- Copy GetSubtitle command.
- Save TOML workflow.

### Phase 4: Local bridge

- Add Native Messaging host or localhost bridge.
- Pair extension with local GetSubtitle.
- Send manifest to GetSubtitle.
- Show run progress and output folder.

### Phase 5: Learner polish

- asbplayer-focused VTT export guidance.
- Multi-episode batch progress.
- Better manual-search links per language.
- Better warnings for 4+ language subtitle files.

## Recommended first implementation

Start without a Chrome extension:

1. Add a generic manifest schema.
2. Add `getsubtitle --manifest manifest.json`.
3. Improve Netflix URL metadata and alias handling.
4. Add a small `scripts/netflix_manifest_example.json`.
5. Document the Netflix/asbplayer workflow.

Then build the Chrome extension once the manifest contract is stable.
