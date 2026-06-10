# API Keys And Subtitle Sources

API keys are optional, but they improve subtitle coverage and enable online
AI translation.

Set keys once:

```sh
getsubtitle --set-key
getsubtitle --set-key jimaku
getsubtitle --set-key wyzie
getsubtitle --set-key subdl
getsubtitle --set-key deepl
getsubtitle --set-key tmdb
```

## Subtitle Sources And Services

| Source/service | Use |
|---|---|
| Jimaku | Japanese anime subtitles |
| Wyzie | Movies and TV |
| SubDL | Backup subtitle source when Wyzie misses |
| DeepL | Online AI translation |
| TMDB | Title matching and `-e all` for live-action TV |

On macOS, keys are stored in Keychain when available. Otherwise, set environment
variables in your shell:

```sh
JIMAKU_API_KEY
WYZIE_API_KEY
SUBDL_API_KEY
DEEPL_API_KEY
TMDB_API_KEY
```

## AI Translation Engines

| Engine | Local? | Setup | Quality |
|---|---|---|---|
| `argos` | yes | `pip install argostranslate` | gist |
| `ollama` | yes | Ollama daemon + model | good |
| `deepl` | online | `getsubtitle --set-key deepl` | best |

Per-pair Ollama model selection lives in `[translate.ollama_models]` in
`user_settings.toml`. Engine spec accepts colon-form to pin a model:

```sh
ollama:qwen3:8b
```
