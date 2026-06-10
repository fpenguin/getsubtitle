# Examples

Once you have run the wizard a few times, the CLI is faster.

## Easy

Movie by URL: Totoro, Japanese + English.

```sh
getsubtitle "https://www.themoviedb.org/movie/8392" -l ja,en
```

## Medium

Series with Japanese furigana for browser/asbplayer readings above kanji.

```sh
getsubtitle "https://www.imdb.com/title/tt6150576/" \
    -s 1 -e all \
    -l ja,ko \
    --reading ja:hiragana \
    --format vtt
```

## Existing Folder

Merge subtitle files already on disk.

```sh
getsubtitle merge ~/Downloads/Show -l ja,en
```

## Missing Language Tracks

Friends S4E3-5: fill Spanish from French, then merge.

```sh
getsubtitle "https://www.themoviedb.org/tv/1668-friends" -s 4 -e 3-5 -l fr,en,es
getsubtitle translate ~/Downloads/GetSubtitle/Friends -s 4 -e 3-5 -l es \
    --engine deepl --mt-source es:fr
getsubtitle merge ~/Downloads/GetSubtitle/Friends -s 4 -e 3-5 -l fr,en,es
```

For AI translation, `--mt-source "es:fr|en"` means "make Spanish from
French first, then try English if French is not available." Ollama users can pin a per-pair model:

```sh
--mt-model-pair ja:ko=qwen3:4b
```

When Japanese, Korean, or Chinese subtitles are missing, fetch prints community
search suggestions and can open likely sources in your browser.

```sh
--manual-search off|on-missing|always
```

For Chinese learners, request Chinese text with `zh` (or aliases such as
`traditional chinese`, `zh-Hant`, `zh-TW`, `simplified chinese`, `zh-Hans`,
`zh-CN`). Add pronunciation separately:

```sh
# Mandarin pinyin
getsubtitle merge FOLDER -l zh,zh-marks,en

# Cantonese Jyutping from a Chinese subtitle source
getsubtitle merge FOLDER -l yue-numbers,zh,en
```

For non-anime TV, `-e all` needs a TMDB key. Set one once:

```sh
getsubtitle --set-key tmdb
```

Or pass an explicit range:

```sh
-e 1-22
```
