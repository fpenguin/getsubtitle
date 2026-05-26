import runpy
from pathlib import Path


MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "getsubtitle_core.py"), run_name="getsubtitle_test")


def test_catalog_provider_detection():
    assert MODULE["provider_from_host"]("www.imdb.com") == "imdb"
    assert MODULE["provider_from_host"]("www.themoviedb.org") == "tmdb"
    assert MODULE["provider_from_host"]("letterboxd.com") == "letterboxd"


def test_catalog_title_cleanup():
    assert MODULE["clean_catalog_title"]("Spirited Away (2001) - IMDb", "imdb") == "Spirited Away"
    assert MODULE["clean_catalog_title"]("Spirited Away | Rotten Tomatoes", "rottentomatoes") == "Spirited Away"


def test_crunchyroll_marketing_title_is_ignored():
    assert MODULE["clean_page_title"]("Crunchyroll: Watch Popular Anime, Play Games & Shop Online") == ""


def test_release_source_detection():
    assert MODULE["normalized_release_source"]("Movie.2020.1080p.WEBRip.NF") == "netflix"
    assert MODULE["normalized_release_source"]("Show.WEB-DL.CR") == "crunchyroll"
    assert MODULE["normalized_release_source"]("Movie.1080p.BluRay") == "bluray"


def test_language_aliases():
    assert MODULE["split_csv"]("ja,ko,en,sp", "ja") == ["ja", "ko", "en", "es"]
    assert MODULE["split_csv"]("japanese,korean,english,spanish", "ja") == ["ja", "ko", "en", "es"]


def test_choose_best_prefers_source_and_srt():
    subtitle = MODULE["SubtitleFile"]
    files = [
        subtitle("wyzie", "en", "movie.bluray.en.srt", "u", release_source="bluray"),
        subtitle("wyzie", "en", "movie.netflix.en.ass", "u", release_source="netflix"),
        subtitle("wyzie", "en", "movie.netflix.en.srt", "u", release_source="netflix"),
    ]
    assert MODULE["choose_best"](files, "netflix").name == "movie.netflix.en.srt"


def test_tmdb_id_from_url():
    media = MODULE["infer_from_catalog_url"]("https://www.themoviedb.org/movie/129", "tmdb")
    assert media.tmdb_id == "129"


def test_summarize_episodes_compacts_ranges():
    assert MODULE["summarize_episodes"](["1", "2", "3", "7", "9", "10"]) == "1-3, 7, 9-10"


def test_summarize_episode_labels_compacts_ranges():
    assert MODULE["summarize_episode_labels"](["1", "2", "3", "7", "9", "10"]) == "E01-E03, E07, E09-E10"


def test_slug_to_title_preserves_acronyms():
    # Short consonant-only tokens become acronyms.
    assert MODULE["slug_to_title"]("mf-ghost") == "MF Ghost"
    assert MODULE["slug_to_title"]("tv-anime") == "TV Anime"
    # Regular short words with vowels stay title-cased so we don't mangle them.
    assert MODULE["slug_to_title"]("of-mice-and-men") == "Of Mice And Men"
    # Longer all-consonant words (rare) are not treated as acronyms.
    assert MODULE["slug_to_title"]("crwth") == "Crwth"


def test_anilist_url_extracts_id():
    media = MODULE["infer_from_anilist_url"](
        "https://anilist.co/anime/189046/ReZero-kara-Hajimeru-Isekai-Seikatsu-4th-Season/"
    )
    assert media.provider == "anilist"
    assert media.anilist_id == 189046
    # Slug becomes a human-readable title fallback.
    assert media.title and media.title.lower().startswith("rezero")


def test_anilist_url_unknown_shape_does_not_crash():
    media = MODULE["infer_from_anilist_url"]("https://anilist.co/")
    assert media.provider == "anilist"
    assert media.anilist_id is None
    assert media.title is None


def test_netflix_id_from_url_handles_known_shapes():
    nid = MODULE["netflix_id_from_url"]
    assert nid("https://www.netflix.com/browse?jbv=81700182") == "81700182"
    assert nid("https://www.netflix.com/browse/genre/34399?jbv=60023642") == "60023642"
    assert nid("https://www.netflix.com/watch/81700182") == "81700182"
    assert nid("https://www.netflix.com/title/81700182") == "81700182"
    # No jbv, no /watch or /title path -> None, not a crash.
    assert nid("https://www.netflix.com/browse") is None


def test_mal_url_extracts_id_in_catalog_inference():
    # infer_from_catalog_url makes an HTML fetch but should still return a
    # MediaInfo with mal_id parsed from the path even if HTML is unreachable.
    media = MODULE["infer_from_catalog_url"](
        "https://myanimelist.net/anime/30/Neon_Genesis_Evangelion", "myanimelist"
    )
    assert media.provider == "myanimelist"
    assert media.mal_id == "30"


def test_infer_media_routes_anilist_urls():
    media = MODULE["infer_media"](
        "https://anilist.co/anime/189046/ReZero-kara-Hajimeru-Isekai-Seikatsu-4th-Season/"
    )
    assert media.provider == "anilist"
    assert media.anilist_id == 189046


# runpy.run_path returns a snapshot of globals, but each function's
# __globals__ points to the original live namespace. To monkeypatch a helper
# (like request_json) we go through __globals__.
_SCRIPT_GLOBALS = MODULE["external_ids_from_netflix_id"].__globals__


def _patch_request_json(fake):
    saved = _SCRIPT_GLOBALS["request_json"]
    _SCRIPT_GLOBALS["request_json"] = fake
    return saved


def _restore_request_json(saved):
    _SCRIPT_GLOBALS["request_json"] = saved


def test_external_ids_from_netflix_id_parses_sparql_response():
    # Mock the Wikidata SPARQL response shape and assert we extract every field
    # correctly. Catches typos in field names without hitting the network.
    fake_response = {
        "results": {
            "bindings": [
                {
                    "itemLabel": {"value": "Test Show"},
                    "imdb": {"value": "tt1234567"},
                    "tmdbTv": {"value": "98765"},
                    "tvdb": {"value": "424242"},
                }
            ]
        }
    }
    saved = _patch_request_json(lambda url, **kwargs: fake_response)
    try:
        title, imdb_id, tmdb_id, tvdb_id = MODULE["external_ids_from_netflix_id"]("81700182")
    finally:
        _restore_request_json(saved)
    assert title == "Test Show"
    assert imdb_id == "tt1234567"
    assert tmdb_id == "98765"
    assert tvdb_id == "424242"


def test_external_ids_from_netflix_id_handles_movie_only_response():
    fake_response = {
        "results": {
            "bindings": [
                {
                    "itemLabel": {"value": "Spirited Away"},
                    "tmdbMovie": {"value": "129"},
                }
            ]
        }
    }
    saved = _patch_request_json(lambda url, **kwargs: fake_response)
    try:
        title, imdb_id, tmdb_id, tvdb_id = MODULE["external_ids_from_netflix_id"]("60023642")
    finally:
        _restore_request_json(saved)
    assert title == "Spirited Away"
    assert imdb_id is None
    assert tmdb_id == "129"
    assert tvdb_id is None


def test_external_ids_from_netflix_id_handles_empty_response():
    saved = _patch_request_json(lambda url, **kwargs: {"results": {"bindings": []}})
    try:
        result = MODULE["external_ids_from_netflix_id"]("00000000")
    finally:
        _restore_request_json(saved)
    assert result == (None, None, None, None)


def test_fetch_anilist_info_collects_title_aliases():
    fake_response = {
        "data": {
            "Media": {
                "id": 16498,
                "title": {
                    "romaji": "Shingeki no Kyojin",
                    "english": "Attack on Titan",
                    "native": "進撃の巨人",
                },
                "synonyms": ["진격의 거인", "AoT"],
                "episodes": 25,
            }
        }
    }
    saved = _patch_request_json(lambda url, **kwargs: fake_response)
    try:
        info = MODULE["fetch_anilist_info"](16498)
    finally:
        _restore_request_json(saved)
    assert info.title == "Shingeki no Kyojin"
    assert info.title_aliases == ["Attack on Titan", "進撃の巨人", "진격의 거인", "AoT"]


def test_media_title_queries_preserves_main_then_aliases():
    media = MODULE["MediaInfo"](
        source_url="x",
        provider="test",
        title="Shingeki no Kyojin",
        title_aliases=["Attack on Titan", "進撃の巨人", "진격의 거인", "Attack on Titan"],
    )
    assert MODULE["media_title_queries"](media) == [
        "Shingeki no Kyojin",
        "Attack on Titan",
        "進撃の巨人",
        "진격의 거인",
    ]


def test_lang_matches_accepts_iso_variants():
    m = MODULE["lang_matches"]
    # Korean
    assert m("ko", "ko")
    assert m("ko", "kor")
    assert m("ko", "Korean")
    assert m("ko", "ko-KR")
    # Spanish regional variants
    assert m("es", "es")
    assert m("es", "spa")
    assert m("es", "Spanish")
    assert m("es", "es-LA")
    assert m("es", "es-419")
    assert m("es", "Latin Spanish")
    # English/Japanese sanity
    assert m("en", "English")
    assert m("ja", "jpn")


def test_lang_matches_rejects_other_languages():
    m = MODULE["lang_matches"]
    assert not m("ko", "ja")
    assert not m("ko", "Japanese")
    assert not m("es", "en")
    assert not m("es", "Portuguese")
    # Estonian "et" must not bleed into Spanish "es"
    assert not m("es", "et")
    # Short codes should not substring-match unrelated tokens
    assert not m("es", "test.srt")


def test_lang_matches_uses_filename_tokens():
    m = MODULE["lang_matches"]
    # Filename-style tokens
    assert m("ko", "Show.S01E01.Korean.srt")
    assert m("es", "Show.S01E01.es-LA.WEB-DL.srt")
    assert m("es", "Show.S01E01.Spanish.Latam.srt")


def test_lang_matches_handles_empty_and_aliases():
    m = MODULE["lang_matches"]
    assert not m("ko", None)
    assert not m("ko", "")
    # Targets via aliases too
    assert m("japanese", "ja")
    assert m("kr", "Korean")


def test_wyzie_uses_broad_call_and_filters_locally():
    # Verifies the new strategy: one Wyzie call per episode returns all
    # languages; we filter locally by lang_matches and reuse the cache for
    # subsequent language requests on the same episode.
    wyzie_globals = MODULE["WyzieProvider"].files.__globals__
    saved_request = wyzie_globals["request_json"]
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append(url)
        # Return mixed-language items. Note that Korean is tagged "Korean"
        # (not "ko") and Spanish "es-LA" — strict 2-letter filtering would
        # have missed these.
        return [
            {"url": "https://x/1.srt", "format": "srt", "fileName": "show.ko.srt", "language": "Korean"},
            {"url": "https://x/2.srt", "format": "srt", "fileName": "show.es.srt", "language": "es-LA"},
            {"url": "https://x/3.srt", "format": "srt", "fileName": "show.en.srt", "language": "en"},
        ]

    try:
        wyzie_globals["request_json"] = fake_request_json
        prov = MODULE["WyzieProvider"]("dummy-key")
        media = MODULE["MediaInfo"](
            source_url="https://www.imdb.com/title/tt1234567/",
            provider="imdb",
            imdb_id="tt1234567",
            season="1",
        )
        ko = prov.files(media, "1", "ko")
        es = prov.files(media, "1", "es")
        en = prov.files(media, "1", "en")
        ja = prov.files(media, "1", "ja")  # Not in response -> should be empty
    finally:
        wyzie_globals["request_json"] = saved_request

    assert len(ko) == 1 and ko[0].provider_language == "Korean"
    assert len(es) == 1 and es[0].provider_language == "es-LA"
    assert len(en) == 1
    assert len(ja) == 0  # Nothing Japanese in the broad response -> empty.
    # Broad response was non-empty, so all four lookups reuse the cache: 1 call.
    assert len(calls) == 1, f"expected 1 request, got {len(calls)}: {calls}"


def test_wyzie_retries_with_tmdb_id_when_imdb_returns_nothing():
    # If the IMDb broad call returns nothing, Wyzie should retry with the
    # TMDB ID before giving up. Catches the case where the title indexes
    # differently between the two databases inside Wyzie's backend.
    wyzie_globals = MODULE["WyzieProvider"].files.__globals__
    saved_request = wyzie_globals["request_json"]
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append(url)
        if "id=tt0000000" in url:
            return []  # IMDb broad call: nothing
        if "id=98765" in url:
            return [
                {"url": "https://x/ko.srt", "format": "srt", "fileName": "show.ko.srt", "language": "ko"},
            ]
        return []

    try:
        wyzie_globals["request_json"] = fake_request_json
        prov = MODULE["WyzieProvider"]("dummy-key")
        media = MODULE["MediaInfo"](
            source_url="https://www.imdb.com/title/tt0000000/",
            provider="imdb",
            imdb_id="tt0000000",
            tmdb_id="98765",
            season="1",
        )
        ko = prov.files(media, "1", "ko")
    finally:
        wyzie_globals["request_json"] = saved_request

    assert len(ko) == 1
    # Should have made two broad calls (IMDb then TMDB), no per-language fallback.
    assert len(calls) == 2
    assert "id=tt0000000" in calls[0]
    assert "id=98765" in calls[1]
    # And the broad TMDB call should NOT carry a language= param.
    assert "language=" not in calls[1]


def test_wyzie_does_not_retry_tmdb_when_imdb_has_results():
    # When the IMDb broad call returns items (even if none match the requested
    # language), we should trust it and NOT also query TMDB.
    wyzie_globals = MODULE["WyzieProvider"].files.__globals__
    saved_request = wyzie_globals["request_json"]
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append(url)
        if "id=tt9999999" in url:
            return [{"url": "https://x/en.srt", "format": "srt", "fileName": "show.en.srt", "language": "en"}]
        return [{"url": "https://x/ko.srt", "format": "srt", "fileName": "show.ko.srt", "language": "ko"}]

    try:
        wyzie_globals["request_json"] = fake_request_json
        prov = MODULE["WyzieProvider"]("dummy-key")
        media = MODULE["MediaInfo"](
            source_url="https://www.imdb.com/title/tt9999999/",
            provider="imdb",
            imdb_id="tt9999999",
            tmdb_id="12345",
            season="1",
        )
        ko = prov.files(media, "1", "ko")
    finally:
        wyzie_globals["request_json"] = saved_request

    assert ko == []
    assert len(calls) == 1, "should not query TMDB when IMDb returned items"
    assert "id=tt9999999" in calls[0]


def test_wyzie_falls_back_when_broad_call_returns_nothing():
    # If the broad (no-language) call returns 0 items, we should retry once
    # with the language filter applied (legacy behavior).
    wyzie_globals = MODULE["WyzieProvider"].files.__globals__
    saved_request = wyzie_globals["request_json"]
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append(url)
        if "language=ko" in url:
            return [{"url": "https://x/k.srt", "format": "srt", "fileName": "k.srt", "language": "ko"}]
        return []  # broad call returns nothing

    try:
        wyzie_globals["request_json"] = fake_request_json
        prov = MODULE["WyzieProvider"]("dummy-key")
        media = MODULE["MediaInfo"](
            source_url="https://www.imdb.com/title/tt7654321/",
            provider="imdb",
            imdb_id="tt7654321",
            season="1",
        )
        ko = prov.files(media, "1", "ko")
    finally:
        wyzie_globals["request_json"] = saved_request

    assert len(ko) == 1
    # First call: broad. Second call: per-language fallback.
    assert len(calls) == 2
    assert "language=ko" in calls[1]


def test_parse_anilist_input_recognises_numeric_id():
    pid, title = MODULE["parse_anilist_input"]("143327")
    assert pid == 143327 and title is None
    # Whitespace-tolerant.
    pid, title = MODULE["parse_anilist_input"]("  143327  ")
    assert pid == 143327 and title is None


def test_parse_anilist_input_recognises_anilist_url():
    pid, title = MODULE["parse_anilist_input"]("https://anilist.co/anime/143327/MF-Ghost/")
    assert pid == 143327 and title is None
    # Also handle anilist URLs without a trailing slug.
    pid, title = MODULE["parse_anilist_input"]("https://anilist.co/anime/189046")
    assert pid == 189046 and title is None


def test_parse_anilist_input_treats_text_as_title():
    pid, title = MODULE["parse_anilist_input"]("MF Ghost")
    assert pid is None and title == "MF Ghost"
    # Title containing digits but not purely numeric -> title.
    pid, title = MODULE["parse_anilist_input"]("Re:Zero 4th Season")
    assert pid is None and title == "Re:Zero 4th Season"


def test_parse_anilist_input_blank_returns_none_none():
    assert MODULE["parse_anilist_input"]("") == (None, None)
    assert MODULE["parse_anilist_input"]("   ") == (None, None)


def _make_media(title="Test Show", season="1"):
    return MODULE["MediaInfo"](
        source_url="https://example.com/x",
        provider="example",
        title=title,
        season=season,
    )


def test_subdivx_parser_handles_aadata_json():
    data = {
        "aaData": [
            {"id": 12345, "titulo": "Test.Show.S01E01.SPANISH", "descripcion": "1080p WEB-DL"},
            {"id": 12346, "titulo": "Test.Show.S01E01.Latam", "descripcion": "ES-LA"},
        ]
    }
    subs = MODULE["parse_subdivx_response"](data, _make_media(), "1")
    assert len(subs) == 2
    assert all(s.language == "es" and s.provider == "subdivx" for s in subs)
    # Falls back to descargar.php URL when no explicit url field is present.
    assert subs[0].url.endswith("?id=12345")


def test_subdivx_parser_handles_plain_list_json():
    data = [
        {"id": 99, "title": "Show 01x01", "url": "https://www.subdivx.com/sub99.zip"},
    ]
    subs = MODULE["parse_subdivx_response"](data, _make_media(), "1")
    assert len(subs) == 1
    assert subs[0].url == "https://www.subdivx.com/sub99.zip"


def test_subdivx_parser_handles_html_response():
    html = """
    <html><body>
    <a class="titulo_menu_izq" href="descargar.php?id=77">Test Show S01E01</a>
    <a class="titulo_menu_izq" href="descargar.php?id=78">Test Show S01E02</a>
    <a class="other">Ignore me</a>
    </body></html>
    """
    subs = MODULE["parse_subdivx_response"](html, _make_media(), "1")
    assert len(subs) == 2
    assert subs[0].language == "es"
    assert "id=77" in subs[0].url
    assert "id=78" in subs[1].url


def test_subdivx_provider_tries_title_aliases_until_found():
    provider = MODULE["SubdivxProvider"](enabled=True)
    calls = []

    def fake_search(query):
        calls.append(query)
        if "Attack on Titan" in query:
            return [{"id": 88, "title": "Attack on Titan S01E01 Spanish"}]
        return []

    provider._search = fake_search
    media = MODULE["MediaInfo"](
        source_url="x",
        provider="test",
        title="Shingeki no Kyojin",
        title_aliases=["Attack on Titan", "進撃の巨人", "진격의 거인"],
        season="1",
    )
    subs = provider.files(media, "1")
    assert len(subs) == 1
    assert "Shingeki no Kyojin S01E01" in calls[0]
    assert "Attack on Titan S01E01" in calls[1]


def test_tvdb_id_from_html_artworks_cdn():
    html = """
    <html><body>
    <img src="https://artworks.thetvdb.com/banners/series/383320/posters/abc.jpg">
    </body></html>
    """
    assert MODULE["tvdb_id_from_html"](html) == "383320"


def test_tvdb_id_from_html_internal_link():
    html = '<a href="/series/383320/seasons/official/1">Season 1</a>'
    assert MODULE["tvdb_id_from_html"](html) == "383320"


def test_tvdb_id_from_html_data_attribute():
    html = '<div data-series-id="71663">...</div>'
    assert MODULE["tvdb_id_from_html"](html) == "71663"


def test_tvdb_id_from_html_returns_none_when_absent():
    assert MODULE["tvdb_id_from_html"]("<html><body>no ids here</body></html>") is None
    assert MODULE["tvdb_id_from_html"]("") is None


def test_infer_from_catalog_url_extracts_tvdb_id_from_path():
    # Numeric path form: /series/<id>/...
    media = MODULE["infer_from_catalog_url"](
        "https://thetvdb.com/series/383320/seasons/official/1", "thetvdb"
    )
    assert media.tvdb_id == "383320"


def test_anilist_title_fallbacks_generates_prefixes():
    # 'Frieren Beyond Journeys End' -> try 'Frieren Beyond', then 'Frieren'.
    out = MODULE["_anilist_title_fallbacks"]("Frieren Beyond Journeys End")
    assert out == ["Frieren Beyond", "Frieren"]
    # 2-word title -> only 1-word fallback.
    out = MODULE["_anilist_title_fallbacks"]("One Piece")
    assert out == ["One"]
    # 1-word title -> nothing to fall back to.
    assert MODULE["_anilist_title_fallbacks"]("Naruto") == []
    # Whitespace tolerance.
    out = MODULE["_anilist_title_fallbacks"]("  Spy x Family  ")
    assert out == ["Spy x", "Spy"]


def test_resolve_anilist_id_falls_back_to_first_words():
    # When AniList returns no candidates for the full slug title, retry with
    # progressively shorter prefixes until one matches.
    scope = MODULE["resolve_anilist_id"].__globals__
    saved = scope["search_anilist"]
    calls: list[tuple[str, int]] = []

    AniListCandidate = MODULE["AniListCandidate"]

    def fake_search(title, limit=8):
        calls.append((title, limit))
        if title == "Frieren":
            return [AniListCandidate(id=154587, romaji="Sousou no Frieren", english="Frieren: Beyond Journey's End", native="葬送のフリーレン", season_year=2023, episodes=28)]
        return []

    try:
        scope["search_anilist"] = fake_search
        anilist_id = MODULE["resolve_anilist_id"]("Frieren Beyond Journeys End")
    finally:
        scope["search_anilist"] = saved

    assert anilist_id == 154587
    # Should have tried full, then 2-word, then 1-word.
    assert [c[0] for c in calls] == [
        "Frieren Beyond Journeys End",
        "Frieren Beyond",
        "Frieren",
    ]


def test_resolve_anilist_id_returns_first_match_without_fallback():
    # If the full title matches immediately, no fallback queries are made.
    scope = MODULE["resolve_anilist_id"].__globals__
    saved = scope["search_anilist"]
    calls: list[str] = []
    AniListCandidate = MODULE["AniListCandidate"]

    def fake_search(title, limit=8):
        calls.append(title)
        return [AniListCandidate(id=999, romaji=title, english=None, native=None, season_year=None, episodes=None)]

    try:
        scope["search_anilist"] = fake_search
        anilist_id = MODULE["resolve_anilist_id"]("MF Ghost")
    finally:
        scope["search_anilist"] = saved

    assert anilist_id == 999
    assert calls == ["MF Ghost"]  # No fallback needed.


def test_resolve_anilist_id_raises_when_no_fallback_matches():
    scope = MODULE["resolve_anilist_id"].__globals__
    saved = scope["search_anilist"]
    try:
        scope["search_anilist"] = lambda title, limit=8: []
        try:
            MODULE["resolve_anilist_id"]("Some Imaginary Show Title")
        except MODULE["CliError"] as e:
            assert "Some Imaginary Show Title" in str(e)
        else:
            raise AssertionError("expected CliError when nothing matches")
    finally:
        scope["search_anilist"] = saved


# ===========================================================================
# Combine subcommand tests
# ===========================================================================

def test_parse_episode_marker_recognises_formats():
    pem = MODULE["parse_episode_marker"]
    assert pem("MF Ghost - S01E07.ja.srt") == (1, 7)
    assert pem("Show.S1E7.en.srt") == (1, 7)
    assert pem("Show 1x07 en.srt") == (1, 7)
    assert pem("Show.S12E150.en.srt") == (12, 150)
    assert pem("no markers here.srt") is None


def test_is_combined_output_name_detects_hyphenated_lang():
    cob = MODULE["is_combined_output_name"]
    assert cob("Show.S01E07.ja-ko.srt") is True
    assert cob("Show.S01E07.en-es-ko.srt") is True
    assert cob("Show.S01E07.ja-furigana-ko.srt") is True
    assert cob("Show.S01E07.ja.srt") is False
    assert cob("Show.S01E07.ko.mt.srt") is False


def test_is_furigana_output_name():
    f = MODULE["is_furigana_output_name"]
    assert f("Show.S01E07.ja.furigana-hiragana.asb.srt") is True
    assert f("Show.S01E07.ja.furigana-romaji.lines.ass") is True
    assert f("Show.S01E07.ja.srt") is False


def test_parse_srt_filename_extracts_language_and_mt_flag():
    p = MODULE["parse_srt_filename"]
    assert p("Show.S01E07.ja.srt") == (1, 7, "ja", False)
    assert p("Show.S01E07.ko.mt.srt") == (1, 7, "ko", True)
    assert p("Show.1x07.en.srt") == (1, 7, "en", False)
    # Combined and furigana variants must NOT be classified as single-language.
    assert p("Show.S01E07.ja-ko.srt") is None
    assert p("Show.S01E07.ja.furigana-hiragana.asb.srt") is None
    assert p("Show.S01E07.srt") is None  # no language token
    assert p("Show.txt") is None         # wrong extension


def test_scan_srt_files_ignores_combined_and_furigana_outputs():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # Plant a mix of files. Only the single-lang non-furigana ones
        # should come back.
        files = [
            "Show.S01E07.ja.srt",
            "Show.S01E07.ko.srt",
            "Show.S01E07.en.srt",
            "Show.S01E07.ja-ko.srt",           # combined output -> skip
            "Show.S01E07.ja.furigana-hiragana.asb.srt",  # furigana -> skip
            "Show.S01E07.ko.mt.srt",           # MT -> include
        ]
        for name in files:
            (root / name).write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
            )
        scanned = MODULE["scan_srt_files"]([root])
        names = sorted(p.name for p, *_ in scanned)
    assert names == [
        "Show.S01E07.en.srt",
        "Show.S01E07.ja.srt",
        "Show.S01E07.ko.mt.srt",
        "Show.S01E07.ko.srt",
    ]


def test_group_srts_prefers_non_mt_when_both_exist():
    from pathlib import Path
    scanned = [
        (Path("a/Show.S01E07.ko.mt.srt"), 1, 7, "ko", True),
        (Path("a/Show.S01E07.ko.srt"),    1, 7, "ko", False),
        (Path("a/Show.S01E07.ja.srt"),    1, 7, "ja", False),
    ]
    grouped = MODULE["group_srts_by_episode"](scanned)
    assert grouped[(1, 7)]["ko"].name == "Show.S01E07.ko.srt"
    assert grouped[(1, 7)]["ja"].name == "Show.S01E07.ja.srt"


def test_parse_srt_time_line_returns_milliseconds():
    pl = MODULE["parse_srt_time_line"]
    assert pl("00:00:01,500 --> 00:00:02,750") == (1500, 2750)
    # Comma or dot decimal separator both accepted.
    assert pl("00:00:01.500 --> 00:00:02.750") == (1500, 2750)
    # Hour + extras tolerated.
    assert pl("00:01:00,000 --> 00:01:01,000") == (60000, 61000)


def test_overlap_ratio_handles_basic_cases():
    o = MODULE["overlap_ratio"]
    # Identical -> 1.0
    assert o(0, 1000, 0, 1000) == 1.0
    # No overlap -> 0.0
    assert o(0, 1000, 2000, 3000) == 0.0
    # 50% overlap of shorter
    assert o(0, 1000, 500, 1500) == 0.5
    # Contained
    assert o(0, 1000, 200, 800) == 1.0
    # Negative or zero durations
    assert o(500, 500, 0, 1000) == 0.0


def test_is_dialogue_cue_rejects_credit_and_url_noise():
    SrtCue = MODULE["SrtCue"]
    is_dialogue = MODULE["is_dialogue_cue"]
    assert is_dialogue(SrtCue("1", "00:00:01,000 --> 00:00:02,000", ["Hello there"])) is True
    assert is_dialogue(SrtCue("2", "00:00:01,000 --> 00:00:02,000", ["Subtitles by Example Team"])) is False
    assert is_dialogue(SrtCue("3", "00:00:01,000 --> 00:00:02,000", ["www.example.com"])) is False
    assert is_dialogue(SrtCue("4", "00:00:01,000 --> 00:00:02,000", ["♪ ♬ ♪"])) is False


def test_combine_cues_preserves_lang_order_ja_then_ko():
    SrtCue = MODULE["SrtCue"]
    master = [
        SrtCue("1", "00:00:01,000 --> 00:00:03,000", ["彼女に運命を占ってもらいたい", "人間の列は 引きも切らない"]),
    ]
    targets = {
        "ko": [
            SrtCue("1", "00:00:01,100 --> 00:00:02,900", ["그녀에게 점을 보려는", "사람들의 행렬이"]),
        ],
    }
    combined, rates = MODULE["combine_cues"](
        master, targets, ["ja", "ko"], "ja", MODULE["SYNC_PRESETS"]["auto"],
    )
    assert len(combined) == 1
    # Default: each language flattened to one line. JA on top, KO under.
    assert combined[0].text_lines == [
        "彼女に運命を占ってもらいたい 人間の列は 引きも切らない",
        "그녀에게 점을 보려는 사람들의 행렬이",
    ]
    assert rates["ko"] == 1.0


def test_combine_cues_preserves_lang_order_en_es_ko():
    SrtCue = MODULE["SrtCue"]
    master = [SrtCue("1", "00:00:01,000 --> 00:00:02,000", ["Hello"])]
    targets = {
        "es": [SrtCue("1", "00:00:01,000 --> 00:00:02,000", ["Hola"])],
        "ko": [SrtCue("1", "00:00:01,000 --> 00:00:02,000", ["안녕"])],
    }
    combined, rates = MODULE["combine_cues"](
        master, targets, ["en", "es", "ko"], "en", MODULE["SYNC_PRESETS"]["auto"],
    )
    assert combined[0].text_lines == ["Hello", "Hola", "안녕"]


def test_combine_cues_preserve_lines_keeps_original_breaks():
    SrtCue = MODULE["SrtCue"]
    master = [SrtCue("1", "00:00:01,000 --> 00:00:03,000", ["Line A", "Line B"])]
    targets = {
        "ko": [SrtCue("1", "00:00:01,000 --> 00:00:03,000", ["가", "나"])],
    }
    combined, _ = MODULE["combine_cues"](
        master, targets, ["en", "ko"], "en", MODULE["SYNC_PRESETS"]["auto"],
        preserve_lines=True,
    )
    assert combined[0].text_lines == ["Line A", "Line B", "가", "나"]


def test_combine_cues_overlap_threshold_drops_weak_matches():
    SrtCue = MODULE["SrtCue"]
    # Both cues are ~2s long but only overlap by 100ms (from 1.9-2.0s).
    # Overlap / shorter = 100/2000 = 5%, well below the auto 0.35 threshold.
    master = [SrtCue("1", "00:00:00,000 --> 00:00:02,000", ["A"])]
    targets = {
        "ko": [SrtCue("1", "00:00:01,900 --> 00:00:04,000", ["가"])],
    }
    combined, rates = MODULE["combine_cues"](
        master, targets, ["en", "ko"], "en", MODULE["SYNC_PRESETS"]["auto"],
    )
    assert rates["ko"] == 0.0
    # The ko line is omitted; only the master ("A") is present.
    assert combined[0].text_lines == ["A"]


def test_combine_cues_strict_is_stricter_than_loose():
    SrtCue = MODULE["SrtCue"]
    master = [SrtCue("1", "00:00:00,000 --> 00:00:10,000", ["Long master"])]
    # Target cue has 30% overlap with master (300ms / 1000ms shorter is 30%).
    targets = {
        "ko": [SrtCue("1", "00:00:09,700 --> 00:00:10,700", ["가"])],
    }
    _, loose = MODULE["combine_cues"](
        master, targets, ["en", "ko"], "en", MODULE["SYNC_PRESETS"]["loose"],
    )
    _, strict = MODULE["combine_cues"](
        master, targets, ["en", "ko"], "en", MODULE["SYNC_PRESETS"]["strict"],
    )
    assert loose["ko"] == 1.0   # 0.20 threshold accepts 0.30 overlap
    assert strict["ko"] == 0.0  # 0.60 threshold rejects it


def test_estimate_timing_offset_detects_constant_shift():
    SrtCue = MODULE["SrtCue"]
    master = [
        SrtCue("1", "00:00:10,000 --> 00:00:12,000", ["A"]),
        SrtCue("2", "00:00:20,000 --> 00:00:22,000", ["B"]),
        SrtCue("3", "00:00:30,000 --> 00:00:32,000", ["C"]),
    ]
    target = [
        SrtCue("1", "00:00:01,000 --> 00:00:03,000", ["A ko"]),
        SrtCue("2", "00:00:11,000 --> 00:00:13,000", ["B ko"]),
        SrtCue("3", "00:00:21,000 --> 00:00:23,000", ["C ko"]),
    ]
    assert MODULE["estimate_timing_offset_ms"](master, target, MODULE["SYNC_PRESETS"]["auto"]) == 9000


def test_estimate_timing_offset_ignores_subtitle_credit_cues():
    SrtCue = MODULE["SrtCue"]
    master = [
        SrtCue("1", "00:00:01,000 --> 00:00:03,000", ["Subtitles by Example Team"]),
        SrtCue("2", "00:00:10,000 --> 00:00:12,000", ["A"]),
        SrtCue("3", "00:00:20,000 --> 00:00:22,000", ["B"]),
        SrtCue("4", "00:00:30,000 --> 00:00:32,000", ["C"]),
    ]
    target = [
        SrtCue("1", "00:00:05,000 --> 00:00:07,000", ["www.example.com"]),
        SrtCue("2", "00:00:01,000 --> 00:00:03,000", ["A ko"]),
        SrtCue("3", "00:00:11,000 --> 00:00:13,000", ["B ko"]),
        SrtCue("4", "00:00:21,000 --> 00:00:23,000", ["C ko"]),
    ]
    assert MODULE["estimate_timing_offset_ms"](master, target, MODULE["SYNC_PRESETS"]["auto"]) == 9000


def test_combine_cues_applies_constant_offset_before_matching():
    SrtCue = MODULE["SrtCue"]
    master = [
        SrtCue("1", "00:00:10,000 --> 00:00:12,000", ["A"]),
        SrtCue("2", "00:00:20,000 --> 00:00:22,000", ["B"]),
        SrtCue("3", "00:00:30,000 --> 00:00:32,000", ["C"]),
    ]
    target = [
        SrtCue("1", "00:00:01,000 --> 00:00:03,000", ["A ko"]),
        SrtCue("2", "00:00:11,000 --> 00:00:13,000", ["B ko"]),
        SrtCue("3", "00:00:21,000 --> 00:00:23,000", ["C ko"]),
    ]
    combined, rates = MODULE["combine_cues"](
        master, {"ko": target}, ["ja", "ko"], "ja", MODULE["SYNC_PRESETS"]["auto"],
    )
    assert rates["ko"] == 1.0
    assert combined[0].text_lines == ["A", "A ko"]
    assert combined[1].text_lines == ["B", "B ko"]


def test_combine_cues_stacks_japanese_furigana_without_flattening_other_langs():
    SrtCue = MODULE["SrtCue"]
    combine_globals = MODULE["combine_cues"].__globals__
    original_kanji_reading_pair_lines = combine_globals["kanji_reading_pair_lines"]
    try:
        combine_globals["kanji_reading_pair_lines"] = lambda text, mode: ("かたぎり", "片桐 君")
        master = [
            SrtCue("1", "00:00:10,000 --> 00:00:12,000", ["片桐 君"]),
        ]
        target = [
            SrtCue("1", "00:00:10,000 --> 00:00:12,000", ["line one", "line two"]),
        ]
        combined, rates = MODULE["combine_cues"](
            master,
            {"en": target},
            ["ja", "en"],
            "ja",
            MODULE["SYNC_PRESETS"]["auto"],
            japanese_furigana_mode="hiragana",
        )
    finally:
        combine_globals["kanji_reading_pair_lines"] = original_kanji_reading_pair_lines

    assert rates["en"] == 1.0
    assert combined[0].text_lines == ["かたぎり", "片桐 君", "line one line two"]


def test_kanji_reading_pair_lines_aligns_rows_to_same_display_width():
    pair = MODULE["kanji_reading_pair_lines"]("特に足回りの仕上げ", "hiragana")
    assert pair is not None
    reading, text = pair
    assert "とく" in reading
    assert "あしまわ" in reading
    assert "特" in text
    assert MODULE["display_cells"](reading) == MODULE["display_cells"](text)


def test_combine_cues_does_not_reuse_same_target_cue():
    SrtCue = MODULE["SrtCue"]
    master = [
        SrtCue("1", "00:00:10,000 --> 00:00:11,000", ["A"]),
        SrtCue("2", "00:00:11,000 --> 00:00:12,000", ["B"]),
    ]
    target = [
        SrtCue("1", "00:00:10,000 --> 00:00:12,000", ["A and B ko"]),
    ]
    combined, rates = MODULE["combine_cues"](
        master, {"ko": target}, ["ja", "ko"], "ja", MODULE["SYNC_PRESETS"]["auto"],
    )
    assert rates["ko"] == 0.5
    assert combined[0].text_lines == ["A", "A and B ko"]
    assert combined[1].text_lines == ["B"]


def test_combined_output_name_basic_and_furigana():
    from pathlib import Path
    n = MODULE["combined_output_name"]
    assert n(Path("/x/MF Ghost - S01E07.ja.srt"), ["ja", "ko"]) == "MF Ghost - S01E07.ja-ko.srt"
    assert n(Path("/x/Show.S02E03.en.srt"), ["en", "es", "ko"]) == "Show.S02E03.en-es-ko.srt"
    # Furigana variant rewrites ja -> ja-furigana.
    assert n(Path("/x/MF Ghost - S01E07.ja.srt"), ["ja", "ko"], furigana=True) == "MF Ghost - S01E07.ja-furigana-ko.srt"
    # MT source stem still strips cleanly.
    assert n(Path("/x/Show.S01E07.ko.mt.srt"), ["ko", "ja"]) == "Show.S01E07.ko-ja.srt"
    p = MODULE["combined_output_path"]
    assert p(Path("/x/MF Ghost - S01E07.ja.srt"), ["ja", "ko"], furigana=True, fmt="vtt") == "MF Ghost - S01E07.ja-furigana-ko.vtt"


def test_combine_main_dry_run_summary_and_no_writes():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E07.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nこんにちは\n", encoding="utf-8"
        )
        (root / "Show.S01E07.ko.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n안녕하세요\n", encoding="utf-8"
        )
        rc = MODULE["combine_main"]([str(root), "-l", "ja,ko", "--dry-run"])
        assert rc == 0
        # No combined file should have been written.
        assert not any(p.name.endswith(".ja-ko.srt") for p in root.iterdir())


def test_combine_main_writes_combined_file():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E07.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n彼女に運命を占ってもらいたい\n人間の列は 引きも切らない\n",
            encoding="utf-8",
        )
        (root / "Show.S01E07.ko.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n그녀에게 점을 보려는\n사람들의 행렬이\n",
            encoding="utf-8",
        )
        rc = MODULE["combine_main"]([str(root), "-l", "ja,ko"])
        assert rc == 0
        out = root / "Show.S01E07.ja-ko.srt"
        assert out.exists()
        body = out.read_text(encoding="utf-8")
        # Flattened, in lang order.
        assert "彼女に運命を占ってもらいたい 人間の列は 引きも切らない" in body
        assert "그녀에게 점을 보려는 사람들의 행렬이" in body


def test_combine_main_open_folder_flag_opens_output_folder():
    import tempfile
    from pathlib import Path

    opened = []
    scope = MODULE["combine_main"].__globals__
    saved_open_folder = scope["open_folder"]
    try:
        scope["open_folder"] = lambda path: opened.append(Path(path))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Show.S01E07.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:03,000\nこんにちは\n", encoding="utf-8"
            )
            (root / "Show.S01E07.ko.srt").write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n안녕하세요\n", encoding="utf-8"
            )
            rc = MODULE["combine_main"]([str(root), "-l", "ja,ko", "--open-folder"])
            assert rc == 0
            assert opened == [root]
    finally:
        scope["open_folder"] = saved_open_folder


def test_combine_main_writes_vtt_with_ruby_furigana():
    import tempfile
    from pathlib import Path

    combine_scope = MODULE["combine_main"].__globals__
    saved_apply_japanese_ruby = combine_scope["apply_japanese_ruby"]
    try:
        def fake_apply(cues, mode):
            for cue in cues:
                cue.text_lines = [line.replace("片桐", "<ruby>片桐<rt>かたぎり</rt></ruby>") for line in cue.text_lines]

        combine_scope["apply_japanese_ruby"] = fake_apply
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Show.S01E07.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n片桐 君\n", encoding="utf-8"
            )
            (root / "Show.S01E07.ko.srt").write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n카타기리 군\n", encoding="utf-8"
            )
            rc = MODULE["combine_main"]([
                str(root), "-l", "ja,ko", "--furigana", "--format", "vtt",
            ])
            assert rc == 0
            out = root / "Show.S01E07.ja-furigana-ko.vtt"
            assert out.exists()
            body = out.read_text(encoding="utf-8")
            assert body.startswith("WEBVTT\n")
            assert "00:00:01.000 --> 00:00:03.000" in body
            assert "<ruby>片桐<rt>かたぎり</rt></ruby> 君" in body
            assert "카타기리 군" in body
            assert not (root / "Show.S01E07.ja-furigana-ko.srt").exists()
    finally:
        combine_scope["apply_japanese_ruby"] = saved_apply_japanese_ruby


def test_combine_main_episode_filter_writes_only_requested_episode():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for ep in (7, 8):
            (root / f"Show.S01E{ep:02d}.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
            )
            (root / f"Show.S01E{ep:02d}.ko.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\n안녕\n", encoding="utf-8"
            )
        rc = MODULE["combine_main"]([str(root), "-e", "8", "-l", "ja,ko"])
        assert rc == 0
        assert not (root / "Show.S01E07.ja-ko.srt").exists()
        assert (root / "Show.S01E08.ja-ko.srt").exists()


def test_combine_main_season_and_episode_range_filter():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for season, ep in ((1, 1), (2, 1), (2, 2), (2, 3)):
            (root / f"Show.S{season:02d}E{ep:02d}.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
            )
            (root / f"Show.S{season:02d}E{ep:02d}.ko.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\n안녕\n", encoding="utf-8"
            )
        rc = MODULE["combine_main"]([str(root), "-s", "2", "-e", "1-2", "-l", "ja,ko"])
        assert rc == 0
        assert not (root / "Show.S01E01.ja-ko.srt").exists()
        assert (root / "Show.S02E01.ja-ko.srt").exists()
        assert (root / "Show.S02E02.ja-ko.srt").exists()
        assert not (root / "Show.S02E03.ja-ko.srt").exists()


def test_combine_main_force_overwrites_existing():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E07.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
        )
        (root / "Show.S01E07.ko.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n안녕\n", encoding="utf-8"
        )
        out = root / "Show.S01E07.ja-ko.srt"
        out.write_text("EXISTING", encoding="utf-8")
        # Without --force, must not overwrite.
        MODULE["combine_main"]([str(root), "-l", "ja,ko"])
        assert out.read_text(encoding="utf-8") == "EXISTING"
        # With --force, must overwrite.
        MODULE["combine_main"]([str(root), "-l", "ja,ko", "--force"])
        assert out.read_text(encoding="utf-8") != "EXISTING"
        assert "안녕" in out.read_text(encoding="utf-8")


def test_combine_main_master_override_changes_timings():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # ja cue at 1.0-2.0, ko cue at 1.5-2.5; they overlap enough to pair.
        (root / "Show.S01E07.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nJA\n", encoding="utf-8"
        )
        (root / "Show.S01E07.ko.srt").write_text(
            "1\n00:00:01,500 --> 00:00:02,500\nKO\n", encoding="utf-8"
        )
        rc = MODULE["combine_main"]([str(root), "-l", "ja,ko", "--master", "ko"])
        assert rc == 0
        out = root / "Show.S01E07.ja-ko.srt"
        body = out.read_text(encoding="utf-8")
        # Master is ko -> output timing should be ko's 1.5->2.5.
        assert "00:00:01,500 --> 00:00:02,500" in body


def test_combine_main_output_dir_redirects_files():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        out_dir = root / "out"
        (root / "Show.S01E07.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
        )
        (root / "Show.S01E07.ko.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n안녕\n", encoding="utf-8"
        )
        rc = MODULE["combine_main"]([str(root), "-l", "ja,ko", "-o", str(out_dir)])
        assert rc == 0
        assert (out_dir / "Show.S01E07.ja-ko.srt").exists()
        # Not beside the source.
        assert not (root / "Show.S01E07.ja-ko.srt").exists()


def test_combine_main_skips_when_match_rate_below_threshold():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # ja has 3 cues; ko has 1 cue covering only the first -> 1/3 = 33%
        # match rate, below auto threshold.
        (root / "Show.S01E07.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nA\n"
            "\n2\n00:00:10,000 --> 00:00:11,000\nB\n"
            "\n3\n00:00:20,000 --> 00:00:21,000\nC\n",
            encoding="utf-8",
        )
        (root / "Show.S01E07.ko.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n가\n", encoding="utf-8"
        )
        rc = MODULE["combine_main"]([str(root), "-l", "ja,ko"])
        # Skipped -> no plan, return 1.
        assert rc == 1
        assert not (root / "Show.S01E07.ja-ko.srt").exists()
        # With --force, the file is written anyway.
        rc2 = MODULE["combine_main"]([str(root), "-l", "ja,ko", "--force"])
        assert rc2 == 0
        assert (root / "Show.S01E07.ja-ko.srt").exists()


def test_combine_main_skips_episode_with_entirely_missing_target_language():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # Only ja present; ko entirely missing for this episode. Episode
        # should be skipped (match rate 0%) unless --force is used.
        (root / "Show.S01E07.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
        )
        rc = MODULE["combine_main"]([str(root), "-l", "ja,ko"])
        # Nothing written without --force.
        assert rc == 1
        assert not list(root.glob("*ja-ko.srt"))
        # --force writes anyway, producing a ja-only "combined" file.
        rc2 = MODULE["combine_main"]([str(root), "-l", "ja,ko", "--force"])
        assert rc2 == 0
        out = root / "Show.S01E07.ja-ko.srt"
        assert out.exists()
        assert "hi" in out.read_text(encoding="utf-8")


# ===========================================================================
# user_settings.toml (config) tests
# ===========================================================================
# Each config test isolates itself via the GETSUBTITLE_CONFIG_PATH env var so
# the real ~/.config/getsubtitle/user_settings.toml on a contributor's
# machine can't influence test outcomes.

import os as _os_for_config_tests


def _isolated_config(toml_text: str | None):
    """Context manager returning a Path to a temp config file (or a
    nonexistent path when toml_text is None). Sets GETSUBTITLE_CONFIG_PATH for
    the duration."""
    import contextlib
    import tempfile
    from pathlib import Path

    @contextlib.contextmanager
    def _cm():
        prev = _os_for_config_tests.environ.get("GETSUBTITLE_CONFIG_PATH")
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "user_settings.toml"
            if toml_text is not None:
                target.write_text(toml_text, encoding="utf-8")
            _os_for_config_tests.environ["GETSUBTITLE_CONFIG_PATH"] = str(target)
            try:
                yield target
            finally:
                if prev is None:
                    _os_for_config_tests.environ.pop("GETSUBTITLE_CONFIG_PATH", None)
                else:
                    _os_for_config_tests.environ["GETSUBTITLE_CONFIG_PATH"] = prev

    return _cm()


def test_config_no_file_returns_empty():
    with _isolated_config(None):
        assert MODULE["load_user_config"]() == {}


def test_config_path_env_override():
    from pathlib import Path
    with _isolated_config(None) as path:
        assert MODULE["config_path"]() == Path(str(path))


def test_config_path_default_per_platform():
    # When GETSUBTITLE_CONFIG_PATH is unset, the path should land under
    # ~/.config/getsubtitle/ on Linux/macOS or %APPDATA%\getsubtitle on Windows.
    prev = _os_for_config_tests.environ.pop("GETSUBTITLE_CONFIG_PATH", None)
    prev_xdg = _os_for_config_tests.environ.pop("XDG_CONFIG_HOME", None)
    try:
        p = str(MODULE["config_path"]())
    finally:
        if prev is not None:
            _os_for_config_tests.environ["GETSUBTITLE_CONFIG_PATH"] = prev
        if prev_xdg is not None:
            _os_for_config_tests.environ["XDG_CONFIG_HOME"] = prev_xdg
    assert p.endswith("user_settings.toml")
    assert "getsubtitle" in p


def test_config_validates_layout_enum():
    bad = '[download]\nlayout = "totally-bogus"\n'
    with _isolated_config(bad):
        try:
            MODULE["load_user_config"]()
        except MODULE["CliError"] as e:
            assert "download.layout" in str(e)
        else:
            raise AssertionError("expected CliError for invalid layout")


def test_config_validates_boolean_type():
    bad = '[download]\nsingle_line = "yes"\n'
    with _isolated_config(bad):
        try:
            MODULE["load_user_config"]()
        except MODULE["CliError"] as e:
            assert "download.single_line" in str(e)
            assert "boolean" in str(e).lower()
        else:
            raise AssertionError("expected CliError for non-bool")


def test_config_validates_translate_engine():
    bad = '[translate]\nengine = "googletranslate"\n'
    with _isolated_config(bad):
        try:
            MODULE["load_user_config"]()
        except MODULE["CliError"] as e:
            assert "translate.engine" in str(e)
        else:
            raise AssertionError("expected CliError for bad engine")


def test_config_accepts_ollama_models_nested_table():
    toml = '[translate]\nmodel = "aya-expanse:8b"\n[translate.ollama_models]\n"ja:ko" = "qwen3:4b"\nen-es = "llama3.2:3b"\n'
    with _isolated_config(toml):
        cfg = MODULE["load_user_config"]()
        assert cfg["translate"]["ollama_models"] == {
            "ja-ko": "qwen3:4b",
            "en-es": "llama3.2:3b",
        }
        assert MODULE["ollama_model_for_pair"]("ja", "ko") == "qwen3:4b"
        assert MODULE["ollama_model_for_pair"]("en", "es") == "llama3.2:3b"
        assert MODULE["ollama_model_for_pair"]("ja", "en") == "aya-expanse:8b"
        assert MODULE["ollama_model_for_pair"]("ja", "ko", cli_model="qwen2.5:3b") == "qwen2.5:3b"


def test_config_validates_ollama_models_pair_keys():
    bad = '[translate.ollama_models]\njapanese_to_korean = "qwen3:4b"\n'
    with _isolated_config(bad):
        try:
            MODULE["load_user_config"]()
        except MODULE["CliError"] as e:
            assert "translate.ollama_models" in str(e)
        else:
            raise AssertionError("expected CliError for bad ollama model pair key")


def test_config_accepts_langs_as_string_or_array():
    toml = (
        '[download]\nlangs = "ja,ko"\n'
        '[combine]\nlangs = ["ja", "ko", "en"]\n'
    )
    with _isolated_config(toml):
        cfg = MODULE["load_user_config"]()
    assert cfg["download"]["langs"] == "ja,ko"
    # Arrays are normalised to a comma-separated string for argparse.
    assert cfg["combine"]["langs"] == "ja,ko,en"


def test_config_combine_priority_parsed_as_lowercase_list():
    toml = '[combine]\npriority = ["JA", "En", "ko"]\n'
    with _isolated_config(toml):
        cfg = MODULE["load_user_config"]()
    assert cfg["combine"]["priority"] == ["ja", "en", "ko"]


def test_config_combine_priority_rejects_non_list():
    bad = '[combine]\npriority = "ja,en"\n'
    with _isolated_config(bad):
        try:
            MODULE["load_user_config"]()
        except MODULE["CliError"] as e:
            assert "combine.priority" in str(e)
        else:
            raise AssertionError("expected CliError for non-list priority")


def test_config_default_lang_applies_to_download_parser():
    toml = '[download]\nlangs = "ja,ko,en"\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        # No -l passed -> takes config default.
        args = parser.parse_args(["https://www.imdb.com/title/tt0245429/"])
        assert args.langs == "ja,ko,en"


def test_cli_lang_overrides_config_lang():
    toml = '[download]\nlangs = "ja,ko,en"\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL", "-l", "es"])
        assert args.langs == "es"


def test_config_output_path_is_expanded():
    toml = '[download]\noutput = "~/Subtitles/CustomFolder"\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL"])
    # ~ should have been expanded.
    assert "~" not in args.output
    assert args.output.endswith("Subtitles/CustomFolder")


def test_config_combine_langs_applies_to_combine_parser():
    toml = '[combine]\nlangs = "en,es,ko"\n'
    with _isolated_config(toml):
        parser = MODULE["build_combine_parser"]()
        args = parser.parse_args(["/tmp/x"])
        assert args.langs == "en,es,ko"


def test_config_combine_sync_applies_default():
    toml = '[combine]\nsync = "strict"\n'
    with _isolated_config(toml):
        parser = MODULE["build_combine_parser"]()
        args = parser.parse_args(["/tmp/x"])
        assert args.sync == "strict"


def test_combine_single_line_flag_is_explicit_default_and_overrides_preserve_config():
    toml = '[combine]\npreserve_lines = true\n'
    with _isolated_config(toml):
        parser = MODULE["build_combine_parser"]()
        args = parser.parse_args(["/tmp/x", "--single-line"])
        assert args.preserve_lines is False
        args = parser.parse_args(["/tmp/x", "--single"])
        assert args.preserve_lines is False


def test_config_furigana_enabled_default_implies_hiragana():
    toml = '[furigana]\nenabled = true\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL"])
        assert args.furigana == "hiragana"


def test_config_furigana_enabled_with_romaji_mode():
    toml = '[furigana]\nenabled = true\nmode = "romaji"\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL"])
        assert args.furigana == "romaji"


def test_config_furigana_combine_carries_mode_to_combine_parser():
    # [furigana].combine controls whether combine inlines furigana. With the
    # new defaults, enabled=true is already on by default — so download also
    # picks up the mode from config. Verify both parsers see the user's mode
    # override.
    toml = '[furigana]\ncombine = true\nmode = "romaji"\n'
    with _isolated_config(toml):
        download_parser = MODULE["build_parser"]()
        download_args = download_parser.parse_args(["URL"])
        assert download_args.furigana == "romaji"

        combine_parser = MODULE["build_combine_parser"]()
        combine_args = combine_parser.parse_args(["/tmp/x"])
        assert combine_args.furigana == "romaji"


def test_config_furigana_disabled_explicitly_skips_download():
    # If the user opts out via [furigana].enabled = false, download no longer
    # auto-applies furigana (regardless of BUILTIN default).
    toml = '[furigana]\nenabled = false\ncombine = false\n'
    with _isolated_config(toml):
        download_parser = MODULE["build_parser"]()
        download_args = download_parser.parse_args(["URL"])
        assert download_args.furigana is None

        combine_parser = MODULE["build_combine_parser"]()
        combine_args = combine_parser.parse_args(["/tmp/x"])
        assert combine_args.furigana is None


def test_no_furigana_overrides_config_default():
    toml = '[furigana]\nenabled = true\nmode = "romaji"\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL", "--no-furigana"])
        assert args.furigana is None

        combine_parser = MODULE["build_combine_parser"]()
        combine_args = combine_parser.parse_args(["/tmp/x", "--no-furigana"])
        assert combine_args.furigana is None


def test_config_strip_cc_noise_default_true_applies():
    toml = '[download]\nstrip_cc_noise = true\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL"])
        assert args.strip_cc_noise is True


def test_config_experimental_subdivx_applies():
    toml = '[experimental]\nsubdivx = true\naddic7ed = true\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL"])
        assert args.experimental_subdivx is True
        assert args.experimental_addic7ed is True


def test_config_combine_priority_picks_master_when_no_master_flag():
    # combine.priority = ['ja', 'en'] with -l en,ja,ko should pick ja as master.
    import tempfile
    from pathlib import Path
    toml = '[combine]\npriority = ["ja", "en"]\n'
    with _isolated_config(toml):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for lang in ("ja", "en", "ko"):
                (root / f"Show.S01E01.{lang}.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
                )
            # Capture stdout so we can read the planned output line.
            import io, contextlib
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["combine_main"]([str(root), "-l", "en,ja,ko", "--dry-run"])
            assert rc == 0
            text = out.getvalue()
    # Master line should mention ja (chosen via priority over the default
    # "first in -l" which would have been en).
    assert "master: ja" in text


def test_config_show_never_prints_api_keys():
    rendered = MODULE["render_effective_config"](user_cfg={})
    # The renderer's output is just defaults -> never includes any secret-ish keys.
    for forbidden in ("JIMAKU_API_KEY", "WYZIE_API_KEY", "DEEPL_API_KEY", "api_key", "apikey"):
        assert forbidden not in rendered, f"{forbidden!r} leaked into config --show"


def test_config_subcommand_path_action():
    import io, contextlib
    with _isolated_config(None) as path:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = MODULE["config_main"](["--path"])
        assert rc == 0
        assert str(path) in out.getvalue()


def test_config_subcommand_init_creates_file_then_refuses_overwrite():
    with _isolated_config(None) as path:
        # First init: creates the file.
        assert not path.exists()
        rc = MODULE["config_main"](["--init"])
        assert rc == 0
        assert path.exists()
        first_size = path.stat().st_size
        assert first_size > 0
        # Second init without --force: must refuse, must NOT modify the file.
        path.write_text("MY EDITS\n", encoding="utf-8")
        try:
            MODULE["config_main"](["--init"])
        except MODULE["CliError"] as e:
            assert "exists" in str(e).lower()
        else:
            raise AssertionError("expected CliError when file exists without --force")
        assert path.read_text(encoding="utf-8") == "MY EDITS\n"
        # With --force: overwrites.
        rc = MODULE["config_main"](["--init", "--force"])
        assert rc == 0
        assert path.read_text(encoding="utf-8") != "MY EDITS\n"


def test_config_subcommand_show_includes_all_sections():
    toml = '[download]\nlangs = "ja,ko"\n'
    with _isolated_config(toml):
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = MODULE["config_main"](["--show"])
        assert rc == 0
        text = out.getvalue()
    for section in ("[download]", "[combine]", "[furigana]", "[translate]", "[experimental]"):
        assert section in text
    # User-overridden field should be marked.
    assert "from user_settings.toml" in text
    # The overridden value should appear.
    assert 'langs = "ja,ko"' in text


def test_config_subcommand_rejects_multiple_actions():
    with _isolated_config(None):
        try:
            MODULE["config_main"](["--path", "--show"])
        except MODULE["CliError"] as e:
            assert "exactly one" in str(e).lower()
        else:
            raise AssertionError("expected CliError for multiple actions")


def test_help_includes_config_topic_and_preferences_block():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        MODULE["main"](["--help"])
    text = out.getvalue()
    assert "config --path" in text
    assert "config --init" in text
    assert "--help config" in text


def test_help_topic_config_describes_file_and_precedence():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        MODULE["main"](["--help", "config"])
    text = out.getvalue()
    assert "user_settings.toml" in text
    assert "precedence" in text.lower()
    assert "API keys are NEVER" in text or "API keys" in text


def test_builtin_defaults_applied_when_no_config_present():
    # Without a user config file, the parser still picks up the BUILTIN
    # defaults so the documented "out-of-the-box" behavior matches what
    # `config --show` advertises.
    with _isolated_config(None):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL"])
    assert args.langs == "ja"
    assert args.layout == "archive"
    assert args.release_source == "auto"
    # The four flips: language-learner-friendly defaults on by default.
    assert args.single_line is True
    assert args.strip_cc_noise is True
    assert args.furigana == "hiragana"
    assert args.mt_engine == "argos"
    # Experimental opt-ins stay off by default.
    assert args.experimental_subdivx is False
    assert args.experimental_addic7ed is False


def _capture_main(argv):
    """Run main(argv) and return (exit_code, stdout_text, stderr_text)."""
    import io
    import contextlib
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = MODULE["main"](argv)
    return rc, out.getvalue(), err.getvalue()


def test_main_no_args_prints_short_main_help():
    rc, out, _ = _capture_main([])
    assert rc == 0
    assert "Find and prepare subtitles" in out
    # Must include the topic list.
    assert "getsubtitle --help download" in out
    # Must NOT include the long argparse-style argument table.
    assert "--debug-providers" not in out


def test_main_help_short_form_and_long_form_match():
    _, short_out, _ = _capture_main(["-h"])
    _, long_out, _ = _capture_main(["--help"])
    assert short_out == long_out


def test_help_download_topic_focused():
    rc, out, _ = _capture_main(["--help", "download"])
    assert rc == 0
    assert "Download subtitles" in out
    assert "Supported URL types" in out
    # Cross-topic options must not leak into this page.
    assert "--mt-engine" not in out
    assert "--experimental-subdivx" not in out


def test_help_combine_topic_focused():
    rc, out, _ = _capture_main(["--help", "combine"])
    assert rc == 0
    assert "Combine multiple subtitle languages" in out
    assert "--sync" in out
    assert "--master" in out


def test_combine_subcommand_help_routes_to_combine_topic():
    # 'getsubtitle combine --help' and 'getsubtitle combine -h' should both
    # show the combine topic, not main help.
    rc, out, _ = _capture_main(["combine", "--help"])
    assert rc == 0
    assert "Combine multiple subtitle languages" in out
    rc, out, _ = _capture_main(["combine", "-h"])
    assert rc == 0
    assert "Combine multiple subtitle languages" in out


def test_combine_subcommand_no_args_shows_combine_topic():
    # 'getsubtitle combine' alone — friendlier than an argparse error.
    rc, out, _ = _capture_main(["combine"])
    assert rc == 0
    assert "Combine multiple subtitle languages" in out


def test_help_topic_keys_lists_providers_and_env_vars():
    rc, out, _ = _capture_main(["--help", "keys"])
    assert rc == 0
    assert "jimaku" in out and "wyzie" in out and "deepl" in out
    assert "JIMAKU_API_KEY" in out
    assert "WYZIE_API_KEY" in out
    assert "DEEPL_API_KEY" in out


def test_help_topic_translate_lists_engines():
    rc, out, _ = _capture_main(["--help", "translate"])
    assert rc == 0
    assert "argos" in out and "ollama" in out and "deepl" in out


def test_help_topic_furigana_mentions_modes():
    rc, out, _ = _capture_main(["--help", "furigana"])
    assert rc == 0
    assert "hiragana" in out and "romaji" in out


def test_help_topic_advanced_uses_new_strip_name_and_keeps_aliases():
    rc, out, _ = _capture_main(["--help", "advanced"])
    assert rc == 0
    assert "--strip-cc-noise" in out
    # Compat alias mentioned so existing scripts keep working.
    assert "--strip-cc-arrows" in out


def test_help_unknown_topic_returns_2_with_hint():
    rc, out, err = _capture_main(["--help", "bogus"])
    assert rc == 2
    assert out == ""
    assert "Unknown help topic" in err
    assert "download" in err and "combine" in err  # Lists valid topics.


def test_help_does_not_break_existing_download_flow():
    # Sanity check that the help intercept didn't change the existing parse
    # path. Parse a normal URL invocation directly through the parser.
    parser = MODULE["build_parser"]()
    args = parser.parse_args(["https://www.imdb.com/title/tt0245429/", "-l", "ja,ko"])
    assert args.url == "https://www.imdb.com/title/tt0245429/"
    assert args.langs == "ja,ko"


# ===========================================================================
# translate subcommand (PATH-based MT)
# ===========================================================================

def test_translate_main_dry_run_lists_missing_languages():
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # ja and en already exist; ko and es will be planned for MT.
            (root / "Show.S01E01.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n", encoding="utf-8"
            )
            (root / "Show.S01E01.en.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8"
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,ko,en,es",
                    "--mt-engine", "argos", "--dry-run",
                ])
            text = out.getvalue()
    assert rc == 0
    # Plan should mention both missing targets and their auto-picked sources.
    assert "ja->ko" in text  # ko sourced from ja per priority table
    assert "en->es" in text  # es sourced from en per priority table
    # No write happened.
    assert "Wrote" not in text


def test_translate_main_filters_by_season_and_episode():
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for ep in (10, 11, 12):
                (root / f"Show.S01E{ep:02d}.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n", encoding="utf-8"
                )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["translate_main"]([
                    str(root), "-s", "1", "-e", "11", "-l", "ko",
                    "--mt-engine", "argos", "--dry-run",
                ])
            text = out.getvalue()
    assert rc == 0
    assert "Episodes selected: 1 (S01E11-S01E11)" in text
    assert "S01E11 ja->ko" in text
    assert "S01E10 ja->ko" not in text
    assert "S01E12 ja->ko" not in text


def test_translate_main_writes_mt_files_using_fake_translator():
    # Swap in a deterministic fake translator so the test doesn't need argos.
    import tempfile
    from pathlib import Path

    class _FakeTranslator(MODULE["_BaseTranslator"]):
        name = "fake"
        def is_available(self):
            return True
        def translate_batch(self, texts, source, target):
            return [f"[{target}] {t}" for t in texts]

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        scope["select_translator"] = lambda engine, model: _FakeTranslator()
        with _isolated_config(None):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "Show.S01E07.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n", encoding="utf-8"
                )
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,ko", "--mt-engine", "argos",
                ])
                out_path = root / "Show.S01E07.ko.mt.srt"
                assert rc == 0
                assert out_path.exists()
                body = out_path.read_text(encoding="utf-8")
                assert "[ko] こんにちは" in body
    finally:
        scope["select_translator"] = saved_select


def test_strip_inline_furigana_removes_parenthetical_readings():
    s = MODULE["strip_inline_furigana"]
    # Real-world shape produced by text_with_readings: pykakasi splits each
    # chunk so kanji surfaces are annotated separately from okurigana.
    assert s("特（とく）に足回（あしまわ）りの仕上（しあ）げ") == "特に足回りの仕上げ"
    # Kanji-only surface with hiragana reading.
    assert s("漢字（かんじ）です") == "漢字です"
    # Romaji reading.
    assert s("漢字（kanji）です") == "漢字です"
    # Half-width parens also work.
    assert s("特(とく)に") == "特に"


def test_strip_inline_furigana_is_noop_on_plain_text():
    s = MODULE["strip_inline_furigana"]
    # Plain Japanese without readings is untouched.
    assert s("こんにちは") == "こんにちは"
    assert s("特に足回りの仕上げ") == "特に足回りの仕上げ"
    # Non-Japanese text is untouched.
    assert s("Just plain English") == "Just plain English"
    # Parens around non-reading content (e.g. dialogue) survive.
    assert s("(player shouts)") == "(player shouts)"


def test_furigana_config_validates_strip_before_mt_as_bool():
    # The validator should accept true/false and reject non-bool.
    v = MODULE["validate_user_config"]
    out = v({"furigana": {"strip_before_mt": True}})
    assert out["furigana"]["strip_before_mt"] is True
    out = v({"furigana": {"strip_before_mt": False}})
    assert out["furigana"]["strip_before_mt"] is False
    # Bad value → CliError mentioning the key path.
    err = None
    try:
        v({"furigana": {"strip_before_mt": "yes"}})
    except MODULE["CliError"] as e:
        err = str(e)
    assert err is not None and "furigana.strip_before_mt" in err


def test_translate_srt_file_strips_furigana_when_source_is_ja():
    # Cues with inline 漢字（かんじ） readings should reach the translator
    # already cleaned when source_lang is "ja".
    import tempfile
    from pathlib import Path

    seen_payloads: list[list[str]] = []

    class _CapturingTranslator(MODULE["_BaseTranslator"]):
        name = "capture"
        def is_available(self): return True
        def translate_batch(self, texts, source, target, on_progress=None):
            seen_payloads.append(list(texts))
            return [f"[{target}] {t}" for t in texts]

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "Show.S01E01.ja.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n"
            "特（とく）に足回（あしまわ）りの仕上（しあ）げ\n",
            encoding="utf-8",
        )
        dst = Path(d) / "Show.S01E01.ko.mt.srt"
        n = MODULE["translate_srt_file"](src, dst, _CapturingTranslator(), "ja", "ko")
    assert n == 1
    assert len(seen_payloads) == 1
    # The translator should NOT have seen the parenthetical readings.
    assert seen_payloads[0] == ["特に足回りの仕上げ"]


def test_translate_srt_file_does_not_strip_when_source_is_not_ja():
    # The same parenthetical-looking pattern in a non-ja source must reach
    # the translator unchanged — we only want this behavior for ja sources.
    import tempfile
    from pathlib import Path

    seen: list[list[str]] = []

    class _CapturingTranslator(MODULE["_BaseTranslator"]):
        name = "capture"
        def is_available(self): return True
        def translate_batch(self, texts, source, target, on_progress=None):
            seen.append(list(texts))
            return [t for t in texts]

    with tempfile.TemporaryDirectory() as d:
        # Source is ko; even if the cue happens to contain kanji + parens
        # (legal in Korean text), we must not strip them when source != ja.
        src = Path(d) / "Show.S01E01.ko.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n특히（とくに）\n",
            encoding="utf-8",
        )
        dst = Path(d) / "Show.S01E01.ja.mt.srt"
        MODULE["translate_srt_file"](src, dst, _CapturingTranslator(), "ko", "ja")
    assert seen[0] == ["특히（とくに）"]


def test_translate_srt_file_respects_strip_furigana_false_flag():
    # Caller can explicitly disable the strip even when source is ja.
    import tempfile
    from pathlib import Path

    seen: list[list[str]] = []

    class _CapturingTranslator(MODULE["_BaseTranslator"]):
        name = "capture"
        def is_available(self): return True
        def translate_batch(self, texts, source, target, on_progress=None):
            seen.append(list(texts))
            return list(texts)

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "Show.S01E01.ja.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n特（とく）に\n",
            encoding="utf-8",
        )
        dst = Path(d) / "Show.S01E01.ko.mt.srt"
        MODULE["translate_srt_file"](
            src, dst, _CapturingTranslator(), "ja", "ko", strip_furigana=False,
        )
    assert seen[0] == ["特（とく）に"]


def test_translate_main_strip_before_mt_config_false_passes_through():
    # When [furigana].strip_before_mt = false, the ja source should reach
    # the translator with readings intact.
    import tempfile
    from pathlib import Path

    seen: list[list[str]] = []

    class _CapturingTranslator(MODULE["_BaseTranslator"]):
        name = "fake"
        def is_available(self): return True
        def translate_batch(self, texts, source, target, on_progress=None):
            seen.append(list(texts))
            return [f"[{target}] {t}" for t in texts]

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        scope["select_translator"] = lambda engine, model: _CapturingTranslator()
        toml = "[furigana]\nstrip_before_mt = false\n"
        with _isolated_config(toml):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "Show.S01E01.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\n特（とく）に足回り\n",
                    encoding="utf-8",
                )
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,ko", "--mt-engine", "argos",
                ])
        assert rc == 0
        assert seen and seen[0] == ["特（とく）に足回り"]
    finally:
        scope["select_translator"] = saved_select


def test_validate_ollama_models_accepts_flags_and_pair_mappings():
    v = MODULE["validate_user_config"]
    out = v({"translate": {"ollama_models": {
        "auto_load": True,
        "auto_unload": False,
        "ja:ko": "qwen3:4b",
        "en-es": "llama3.2:3b",
    }}})
    om = out["translate"]["ollama_models"]
    assert om["auto_load"] is True
    assert om["auto_unload"] is False
    # Pair keys are normalised to hyphen form with alias resolution.
    assert om["ja-ko"] == "qwen3:4b"
    assert om["en-es"] == "llama3.2:3b"


def test_validate_ollama_models_rejects_non_bool_flag_and_bad_pair():
    v = MODULE["validate_user_config"]
    for bad in ("yes", 1, "true"):
        err = None
        try:
            v({"translate": {"ollama_models": {"auto_load": bad}}})
        except MODULE["CliError"] as e:
            err = str(e)
        assert err is not None and "auto_load" in err
    # Unknown non-pair key should produce a helpful error listing valid flags.
    err = None
    try:
        v({"translate": {"ollama_models": {"weird_key": "x"}}})
    except MODULE["CliError"] as e:
        err = str(e)
    assert err is not None and "auto_load" in err and "auto_unload" in err


def test_ollama_translator_release_resources_sends_keep_alive_zero():
    # Mock urlopen so the test doesn't need a real Ollama daemon.
    import io, json
    captured = {}

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b""

    def fake_urlopen(req, timeout=10):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp()

    tr = MODULE["OllamaTranslator"](model="qwen3:4b")
    scope = MODULE["OllamaTranslator"].release_resources.__globals__
    saved = scope["urllib"].request.urlopen
    try:
        scope["urllib"].request.urlopen = fake_urlopen
        ok = tr.release_resources()
    finally:
        scope["urllib"].request.urlopen = saved
    assert ok is True
    assert captured["url"].endswith("/api/generate")
    assert captured["body"]["model"] == "qwen3:4b"
    assert captured["body"]["keep_alive"] == 0
    assert captured["body"]["prompt"] == ""


def test_ollama_translator_release_resources_swallows_network_errors():
    # Ollama unreachable shouldn't propagate — best-effort unload.
    import urllib.error

    def fake_urlopen(req, timeout=10):
        raise urllib.error.URLError("connection refused")

    tr = MODULE["OllamaTranslator"](model="qwen3:4b")
    scope = MODULE["OllamaTranslator"].release_resources.__globals__
    saved = scope["urllib"].request.urlopen
    try:
        scope["urllib"].request.urlopen = fake_urlopen
        ok = tr.release_resources()
    finally:
        scope["urllib"].request.urlopen = saved
    assert ok is False  # quietly returned False, did not raise


def test_base_translator_release_resources_is_noop():
    # Argos / DeepL inherit the no-op so callers can be polymorphic.
    argos = MODULE["ArgosTranslator"]()
    deepl = MODULE["DeepLTranslator"](api_key=None)
    assert argos.release_resources() is False
    assert deepl.release_resources() is False


def test_ollama_translator_auto_load_false_raises_on_missing_model():
    # When auto_load=False and the model is missing, we should surface a
    # CLI-friendly error mentioning the manual `ollama pull` workaround.
    tr = MODULE["OllamaTranslator"](model="phantom:99", auto_load=False)
    # Mock installed_models to report the model is missing.
    tr.installed_models = lambda: set()  # type: ignore[method-assign]
    err = None
    try:
        tr.ensure_model_available()
    except MODULE["TranslatorError"] as e:
        err = str(e)
    assert err is not None
    assert "phantom:99" in err
    assert "ollama pull" in err
    assert "auto_load" in err


def test_translate_main_unloads_ollama_when_auto_unload_true():
    # End-to-end: when [translate.ollama_models].auto_unload is true (default),
    # release_resources() is called once per cached translator.
    import tempfile
    from pathlib import Path

    released_models: list[str] = []

    class _FakeOllama(MODULE["_BaseTranslator"]):
        name = "ollama"
        def __init__(self, model):
            self.model = model
        def is_available(self): return True
        def translate_batch(self, texts, source, target, on_progress=None):
            return [f"[{target}] {t}" for t in texts]
        def release_resources(self):
            released_models.append(self.model)
            return True

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        scope["select_translator"] = lambda engine, model: _FakeOllama(model or "default")
        # Default config (no override) → auto_unload defaults to True.
        with _isolated_config(None):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "Show.S01E01.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n", encoding="utf-8"
                )
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,ko", "--mt-engine", "ollama",
                ])
        assert rc == 0
        assert released_models  # at least one model was unloaded
    finally:
        scope["select_translator"] = saved_select


def test_translate_main_skips_unload_when_auto_unload_false():
    # When the user sets auto_unload = false in the config, no release call.
    import tempfile
    from pathlib import Path

    released_models: list[str] = []

    class _FakeOllama(MODULE["_BaseTranslator"]):
        name = "ollama"
        def __init__(self, model):
            self.model = model
        def is_available(self): return True
        def translate_batch(self, texts, source, target, on_progress=None):
            return [f"[{target}] {t}" for t in texts]
        def release_resources(self):
            released_models.append(self.model)
            return True

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        scope["select_translator"] = lambda engine, model: _FakeOllama(model or "default")
        toml = "[translate.ollama_models]\nauto_unload = false\n"
        with _isolated_config(toml):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "Show.S01E01.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n", encoding="utf-8"
                )
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,ko", "--mt-engine", "ollama",
                ])
        assert rc == 0
        assert released_models == []  # nothing was unloaded
    finally:
        scope["select_translator"] = saved_select


def test_select_translator_passes_auto_load_from_config():
    # The factory must thread the config flag into the OllamaTranslator
    # constructor — otherwise auto_load=false in config wouldn't take effect.
    toml = "[translate.ollama_models]\nauto_load = false\n"
    with _isolated_config(toml):
        tr = MODULE["select_translator"]("ollama", "qwen3:4b")
    assert isinstance(tr, MODULE["OllamaTranslator"])
    assert tr.auto_load is False
    # Default config → auto_load True.
    with _isolated_config(None):
        tr = MODULE["select_translator"]("ollama", "qwen3:4b")
    assert tr.auto_load is True


def test_translate_main_uses_pair_specific_ollama_model_from_config():
    import tempfile
    from pathlib import Path

    seen_models = []

    class _FakeTranslator(MODULE["_BaseTranslator"]):
        name = "ollama"
        def __init__(self, model):
            self.model = model
        def is_available(self):
            return True
        def translate_batch(self, texts, source, target, on_progress=None):
            return [f"[{self.model}] {t}" for t in texts]

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        def fake_select(engine, model):
            seen_models.append(model)
            return _FakeTranslator(model)

        scope["select_translator"] = fake_select
        toml = '[translate]\nmodel = "aya-expanse:8b"\n[translate.ollama_models]\n"ja:ko" = "qwen3:4b"\n'
        with _isolated_config(toml):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "Show.S01E07.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n", encoding="utf-8"
                )
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ko", "--mt-engine", "ollama",
                ])
                out_path = root / "Show.S01E07.ko.mt.srt"
                assert rc == 0
                assert "[qwen3:4b] こんにちは" in out_path.read_text(encoding="utf-8")
    finally:
        scope["select_translator"] = saved_select

    assert "qwen3:4b" in seen_models
    assert "aya-expanse:8b" not in seen_models


def test_translate_main_refuses_overwrite_without_force():
    import tempfile
    from pathlib import Path

    class _FakeTranslator(MODULE["_BaseTranslator"]):
        name = "fake"
        def is_available(self): return True
        def translate_batch(self, texts, source, target):
            return [f"NEW {t}" for t in texts]

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        scope["select_translator"] = lambda engine, model: _FakeTranslator()
        with _isolated_config(None):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "Show.S01E07.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nA\n", encoding="utf-8"
                )
                (root / "Show.S01E07.ko.mt.srt").write_text("EXISTING", encoding="utf-8")
                # Without --force: skipped, file untouched.
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,ko", "--mt-engine", "argos",
                ])
                assert (root / "Show.S01E07.ko.mt.srt").read_text(encoding="utf-8") == "EXISTING"
                # With --force: overwritten.
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,ko", "--mt-engine", "argos", "--force",
                ])
                assert rc == 0
                assert (root / "Show.S01E07.ko.mt.srt").read_text(encoding="utf-8") != "EXISTING"
    finally:
        scope["select_translator"] = saved_select


def test_translate_main_errors_when_engine_explicitly_disabled():
    # The default engine is now "argos" (BUILTIN). To trigger the missing-
    # engine path the user has to opt out — either by setting engine = ""
    # in user_settings.toml or by passing --no-mt-engine at the CLI.
    toml = '[translate]\nengine = ""\n'
    with _isolated_config(toml):
        try:
            MODULE["translate_main"](["/tmp/nowhere", "-l", "ja,ko"])
        except MODULE["CliError"] as e:
            assert "engine" in str(e).lower()
        else:
            raise AssertionError("expected CliError when engine = '' in config")


def test_translate_main_errors_when_no_mt_engine_flag_used():
    # --no-mt-engine wins over the BUILTIN argos default.
    with _isolated_config(None):
        try:
            MODULE["translate_main"]([
                "/tmp/nowhere", "-l", "ja,ko", "--no-mt-engine",
            ])
        except MODULE["CliError"] as e:
            assert "engine" in str(e).lower()
        else:
            raise AssertionError("expected CliError when --no-mt-engine passed")


def test_translate_main_errors_when_path_missing():
    with _isolated_config(None):
        try:
            MODULE["translate_main"]([
                "/path/that/definitely/does/not/exist",
                "-l", "ja,ko", "--mt-engine", "argos",
            ])
        except MODULE["CliError"] as e:
            assert "not found" in str(e).lower()
        else:
            raise AssertionError("expected CliError for missing path")


def test_translate_main_returns_1_when_nothing_to_translate():
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # Both target langs already exist as human files; nothing to MT.
            (root / "Show.S01E01.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nA\n", encoding="utf-8"
            )
            (root / "Show.S01E01.ko.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\n안녕\n", encoding="utf-8"
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,ko", "--mt-engine", "argos",
                ])
    assert rc == 1
    assert "Nothing to translate" in out.getvalue()


def test_language_aliases_includes_jp_and_cn_variants():
    aliases = MODULE["LANGUAGE_ALIASES"]
    # jp -> ja (country code → language code) — was already aliased
    assert aliases.get("jp") == "ja"
    # cn / chi / chinese / mandarin → zh — newly added
    assert aliases.get("cn") == "zh"
    assert aliases.get("chi") == "zh"
    assert aliases.get("chinese") == "zh"
    assert aliases.get("mandarin") == "zh"


def test_lang_matches_recognises_cn_for_zh():
    # Subtitle providers commonly tag Chinese files as 'cn', 'zh-cn', 'CHS', etc.
    m = MODULE["lang_matches"]
    assert m("zh", "cn")
    assert m("zh", "CHS")
    assert m("zh", "zh-cn")
    assert m("zh", "zh-TW")
    assert m("zh", "Chinese")


def test_split_csv_resolves_jp_and_cn():
    s = MODULE["split_csv"]
    assert s("jp,cn", "ja") == ["ja", "zh"]
    assert s("chinese,japanese", "ja") == ["zh", "ja"]


def test_parse_mt_source_lang_resolves_jp_alias_in_single_form():
    # Single-token form: 'jp' should resolve to 'ja' for all targets.
    p = MODULE["parse_mt_source_lang"]
    assert p("jp", ["ko", "es"]) == {"ko": "ja", "es": "ja"}


def test_parse_mt_source_lang_resolves_jp_and_cn_in_pairs():
    # Pair form: aliases on both target and source sides.
    # Target 'cn' (alias for zh) must match -l 'zh'; source 'jp' resolves to 'ja'.
    p = MODULE["parse_mt_source_lang"]
    assert p("ko:jp,cn:en", ["ko", "zh"]) == {"ko": "ja", "zh": "en"}


def test_parse_mt_source_lang_none_or_empty_returns_none():
    p = MODULE["parse_mt_source_lang"]
    assert p(None, ["ja", "ko"]) is None
    assert p("", ["ja", "ko"]) is None
    assert p("   ", ["ja", "ko"]) is None


def test_parse_mt_source_lang_single_code_applies_to_all_targets():
    p = MODULE["parse_mt_source_lang"]
    assert p("ja", ["ja", "ko", "es"]) == {"ja": "ja", "ko": "ja", "es": "ja"}
    # Case-insensitive: single token gets lowered, targets get lowered.
    assert p("JA", ["KO", "ES"]) == {"ko": "ja", "es": "ja"}


def test_parse_mt_source_lang_explicit_pairs():
    p = MODULE["parse_mt_source_lang"]
    assert p("ko:ja", ["ja", "ko"]) == {"ko": "ja"}
    assert p("ko:ja,es:en", ["ja", "ko", "en", "es"]) == {"ko": "ja", "es": "en"}
    # Tolerates whitespace around tokens.
    assert p(" ko : ja , es : en ", ["ja", "ko", "en", "es"]) == {"ko": "ja", "es": "en"}


def test_parse_mt_source_lang_ambiguous_comma_list_rejected():
    p = MODULE["parse_mt_source_lang"]
    try:
        p("ja,en", ["ja", "ko", "en", "es"])  # no colons, multiple tokens
    except MODULE["CliError"] as e:
        assert "ambiguous" in str(e).lower()
        assert "ko:ja" in str(e)  # example shown
    else:
        raise AssertionError("expected CliError for ambiguous comma list")


def test_parse_mt_source_lang_target_not_in_langs_rejected():
    p = MODULE["parse_mt_source_lang"]
    try:
        p("de:en", ["ja", "ko"])
    except MODULE["CliError"] as e:
        assert "'de'" in str(e) and "not in -l" in str(e)
    else:
        raise AssertionError("expected CliError for unknown target")


def test_parse_mt_source_lang_duplicate_target_rejected():
    p = MODULE["parse_mt_source_lang"]
    try:
        p("ko:ja,ko:en", ["ja", "ko", "en"])
    except MODULE["CliError"] as e:
        assert "mapped twice" in str(e)
    else:
        raise AssertionError("expected CliError for duplicate target")


def test_parse_mt_source_lang_empty_half_rejected():
    p = MODULE["parse_mt_source_lang"]
    for bad in ("ko:", ":ja", " : "):
        try:
            p(bad, ["ja", "ko"])
        except MODULE["CliError"]:
            pass
        else:
            raise AssertionError(f"expected CliError for {bad!r}")


def test_parse_mt_source_lang_missing_colon_in_pair_rejected():
    p = MODULE["parse_mt_source_lang"]
    try:
        p("ko:ja,en", ["ja", "ko", "en", "es"])  # mix of pair + bare
    except MODULE["CliError"] as e:
        assert "target:source" in str(e)
    else:
        raise AssertionError("expected CliError for mixed shape")


def test_translate_main_explicit_source_mapping_routes_correctly():
    # ja and en exist; ask for ko (via ja) and es (via en) by explicit pair.
    import tempfile
    from pathlib import Path

    class _FakeTranslator(MODULE["_BaseTranslator"]):
        name = "fake"
        def is_available(self): return True
        def translate_batch(self, texts, source, target):
            return [f"[{source}->{target}] {t}" for t in texts]

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        scope["select_translator"] = lambda engine, model: _FakeTranslator()
        with _isolated_config(None):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "Show.S01E01.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nJ\n", encoding="utf-8"
                )
                (root / "Show.S01E01.en.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nE\n", encoding="utf-8"
                )
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,ko,en,es",
                    "--mt-engine", "argos",
                    "--mt-source-lang", "ko:ja,es:en",
                ])
                assert rc == 0
                ko = (root / "Show.S01E01.ko.mt.srt").read_text(encoding="utf-8")
                es = (root / "Show.S01E01.es.mt.srt").read_text(encoding="utf-8")
    finally:
        scope["select_translator"] = saved_select
    # Each target's content was translated FROM the explicitly-mapped source.
    assert "[ja->ko] J" in ko
    assert "[en->es] E" in es


def test_translate_main_forced_source_missing_is_skipped_with_clear_reason():
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # Only ja present, but we force es<-en (en doesn't exist).
            (root / "Show.S01E01.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nJ\n", encoding="utf-8"
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,es",
                    "--mt-engine", "argos",
                    "--mt-source-lang", "es:en",
                    "--dry-run",
                ])
    assert rc == 1  # nothing was planned
    text = out.getvalue()
    assert "es: forced source 'en' not available" in text


def test_translate_main_single_code_source_still_works():
    # Backward-compat: --mt-source-lang ja (no colons) still forces ja for all.
    import tempfile
    from pathlib import Path

    class _FakeTranslator(MODULE["_BaseTranslator"]):
        name = "fake"
        def is_available(self): return True
        def translate_batch(self, texts, source, target):
            return [f"[{source}->{target}] {t}" for t in texts]

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        scope["select_translator"] = lambda engine, model: _FakeTranslator()
        with _isolated_config(None):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "Show.S01E01.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nJ\n", encoding="utf-8"
                )
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,ko",
                    "--mt-engine", "argos",
                    "--mt-source-lang", "ja",
                ])
                assert rc == 0
                ko = (root / "Show.S01E01.ko.mt.srt").read_text(encoding="utf-8")
    finally:
        scope["select_translator"] = saved_select
    assert "[ja->ko] J" in ko


def test_translate_srt_file_invokes_on_progress_per_cue():
    # Confirms cue-level progress is wired all the way through the translator
    # interface. The callback should fire after each cue.
    import tempfile
    from pathlib import Path

    class _CountingTranslator(MODULE["_BaseTranslator"]):
        name = "counting"
        def is_available(self):
            return True
        def translate_batch(self, texts, source, target, on_progress=None):
            out = []
            for i, t in enumerate(texts, start=1):
                out.append(f"[t] {t}")
                if on_progress is not None:
                    on_progress(i, len(texts))
            return out

    progress_calls: list[tuple[int, int]] = []
    src = (
        "1\n00:00:01,000 --> 00:00:02,000\nA\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nB\n\n"
        "3\n00:00:05,000 --> 00:00:06,000\nC\n"
    )
    with tempfile.TemporaryDirectory() as d:
        src_path = Path(d) / "x.en.srt"
        src_path.write_text(src, encoding="utf-8")
        dst_path = Path(d) / "x.es.mt.srt"
        MODULE["translate_srt_file"](
            src_path, dst_path, _CountingTranslator(), "en", "es",
            on_progress=lambda done, total: progress_calls.append((done, total)),
        )
    assert progress_calls == [(1, 3), (2, 3), (3, 3)]


def test_translator_signatures_accept_on_progress_kwarg():
    # Guards against accidental signature regressions in any built-in
    # translator. Each must accept on_progress=None.
    import inspect
    for cls_name in ("ArgosTranslator", "OllamaTranslator", "DeepLTranslator"):
        sig = inspect.signature(MODULE[cls_name].translate_batch)
        assert "on_progress" in sig.parameters, f"{cls_name}.translate_batch lacks on_progress"


def test_translate_main_dedupes_identical_skip_reasons():
    # 5 episodes, all skipped for the same reason -> one summary line listing
    # the affected episodes rather than 5 identical lines.
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # Only ja exists; force es<-en (en missing across the board).
            for ep in range(1, 6):
                (root / f"Show.S01E0{ep}.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nJ\n", encoding="utf-8"
                )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ja,es",
                    "--mt-engine", "argos",
                    "--mt-source-lang", "es:en",
                    "--dry-run",
                ])
            text = out.getvalue()
    assert rc == 1
    # Summary should show ONE deduped line, not 5 identical ones.
    assert "Skipped: 5" in text
    assert "5 episodes" in text
    occurrences = text.count("forced source 'en' not available for this episode")
    assert occurrences == 1, f"reason should appear once in deduped output, got {occurrences}"


# ===========================================================================
# modify subcommand
# ===========================================================================

def test_modify_main_requires_at_least_one_operation():
    import tempfile
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "X.S01E01.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
            )
            try:
                MODULE["modify_main"]([d])
            except MODULE["CliError"] as e:
                assert "at least one operation" in str(e)
            else:
                raise AssertionError("expected CliError when no operations specified")


def test_modify_main_path_not_found():
    with _isolated_config(None):
        try:
            MODULE["modify_main"]([
                "/definitely/nonexistent/folder",
                "--strip-cc-noise",
            ])
        except MODULE["CliError"] as e:
            assert "not found" in str(e).lower()
        else:
            raise AssertionError("expected CliError for missing path")


def test_modify_main_strips_cc_noise_in_place():
    import tempfile
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "Show.S01E01.ja.srt"
            target.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nこんにちは➡\n", encoding="utf-8"
            )
            rc = MODULE["modify_main"]([str(root), "--strip-cc-noise"])
            assert rc == 0
            body = target.read_text(encoding="utf-8")
    assert "➡" not in body
    assert "こんにちは" in body


def test_modify_main_flattens_single_line_in_place():
    import tempfile
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "Show.S01E01.en.srt"
            target.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nLine A\nLine B\n",
                encoding="utf-8",
            )
            rc = MODULE["modify_main"]([str(target), "--single-line"])
            assert rc == 0
            body = target.read_text(encoding="utf-8")
    assert "Line A Line B" in body
    # Both halves should be on one line.
    assert "Line A\nLine B" not in body


def test_modify_main_combines_strip_and_flatten():
    import tempfile
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "Show.S01E01.ja.srt"
            target.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\n《こんな所を\nフルスロットルで…。➡\n",
                encoding="utf-8",
            )
            rc = MODULE["modify_main"]([
                str(target), "--strip-cc-noise", "--single-line",
            ])
            assert rc == 0
            body = target.read_text(encoding="utf-8")
    # Arrow gone AND lines flattened with full-width space (ja).
    assert "➡" not in body
    assert "《こんな所を　フルスロットルで…。" in body


def test_modify_main_dry_run_writes_nothing():
    import tempfile
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "Show.S01E01.ja.srt"
            original = "1\n00:00:01,000 --> 00:00:02,000\nこんにちは➡\n"
            target.write_text(original, encoding="utf-8")
            rc = MODULE["modify_main"]([str(target), "--strip-cc-noise", "--dry-run"])
            assert rc == 0
            # Arrow should still be present — dry-run wrote nothing.
            assert target.read_text(encoding="utf-8") == original


def test_modify_main_ignores_combined_and_furigana_outputs_in_scan():
    # Reusing scan_srt_files means combined and furigana files don't get
    # double-processed. Make sure the scan filter actually excludes them.
    import tempfile
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # Plant: 1 normal ja, 1 combined output, 1 furigana variant
            (root / "Show.S01E01.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nA➡\n", encoding="utf-8"
            )
            combined_orig = "1\n00:00:01,000 --> 00:00:02,000\nB➡\n"
            (root / "Show.S01E01.ja-ko.srt").write_text(combined_orig, encoding="utf-8")
            furigana_orig = "1\n00:00:01,000 --> 00:00:02,000\nC➡\n"
            (root / "Show.S01E01.ja.furigana-hiragana.asb.srt").write_text(
                furigana_orig, encoding="utf-8"
            )
            MODULE["modify_main"]([str(root), "--strip-cc-noise"])
            # Assertions must run inside the with-block; root vanishes after.
            assert "➡" not in (root / "Show.S01E01.ja.srt").read_text(encoding="utf-8")
            assert (root / "Show.S01E01.ja-ko.srt").read_text(encoding="utf-8") == combined_orig
            assert (root / "Show.S01E01.ja.furigana-hiragana.asb.srt").read_text(encoding="utf-8") == furigana_orig


def test_modify_main_dispatches_via_main_and_help_routes():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out), _isolated_config(None):
        rc = MODULE["main"](["modify", "--help"])
    assert rc == 0
    assert "Post-process existing subtitle files" in out.getvalue()

    out = io.StringIO()
    with contextlib.redirect_stdout(out), _isolated_config(None):
        rc = MODULE["main"](["modify"])
    assert rc == 0
    assert "Post-process existing subtitle files" in out.getvalue()


def test_main_help_lists_modify_subcommand():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out), _isolated_config(None):
        MODULE["main"](["--help"])
    text = out.getvalue()
    assert "modify PATH" in text
    assert "getsubtitle --help modify" in text


def test_parse_furigana_formats_default_is_srt_only():
    p = MODULE["parse_furigana_formats"]
    assert p(None) == {"srt"}
    assert p("") == {"srt"}
    assert p("   ") == {"srt"}


def test_parse_furigana_formats_explicit_choices():
    p = MODULE["parse_furigana_formats"]
    assert p("srt") == {"srt"}
    assert p("ass") == {"ass"}
    assert p("vtt") == {"vtt"}
    assert p("srt,ass") == {"srt", "ass"}
    assert p("srt,ass,vtt") == {"srt", "ass", "vtt"}
    # Whitespace + case tolerance
    assert p(" SRT , AsS ") == {"srt", "ass"}


def test_parse_furigana_formats_all_keyword_expands():
    assert MODULE["parse_furigana_formats"]("all") == {"srt", "ass", "vtt"}
    assert MODULE["parse_furigana_formats"]("ALL") == {"srt", "ass", "vtt"}


def test_parse_furigana_formats_unknown_format_rejected():
    try:
        MODULE["parse_furigana_formats"]("srt,mp4")
    except MODULE["CliError"] as e:
        assert "mp4" in str(e)
        assert "srt, ass, vtt" in str(e).lower() or "srt, ass, vtt" in str(e)
        assert "--help furigana" in str(e)
    else:
        raise AssertionError("expected CliError for unknown format")


def test_generate_furigana_respects_formats_argument():
    # The user-reported pain point: 3 files per episode was too much. Verify
    # that generate_furigana only calls the writers whose formats are in the
    # `formats` set. Mock the three writers so this test doesn't require
    # pykakasi (which may not be installed in CI).
    from pathlib import Path

    scope = MODULE["generate_furigana"].__globals__
    saved = (
        scope["srt_to_asbplayer_readings"],
        scope["srt_to_ruby_vtt"],
        scope["srt_to_furigana_lines_ass"],
    )
    calls: list[str] = []
    try:
        scope["srt_to_asbplayer_readings"] = lambda p, m, s=False: (calls.append("srt"), Path("out.asb.srt"))[1]
        scope["srt_to_ruby_vtt"] = lambda p, m, s=False: (calls.append("vtt"), Path("out.ruby.vtt"))[1]
        scope["srt_to_furigana_lines_ass"] = lambda p, m, s=False: (calls.append("ass"), Path("out.lines.ass"))[1]

        # Default (formats=None) should produce ONLY srt — that's the whole
        # point of this change.
        calls.clear()
        out = MODULE["generate_furigana"]([Path("Show.S01E01.ja.srt")], "hiragana")
        assert calls == ["srt"]
        assert [p.name for p in out] == ["out.asb.srt"]

        # Explicit {srt, ass} should produce both, skipping vtt.
        calls.clear()
        out = MODULE["generate_furigana"](
            [Path("Show.S01E01.ja.srt")], "hiragana", False, formats={"srt", "ass"}
        )
        assert sorted(calls) == ["ass", "srt"]
        assert len(out) == 2

        # 'all' equivalent — full set generates all three.
        calls.clear()
        MODULE["generate_furigana"](
            [Path("Show.S01E01.ja.srt")], "hiragana", False, formats={"srt", "ass", "vtt"}
        )
        assert sorted(calls) == ["ass", "srt", "vtt"]
    finally:
        (
            scope["srt_to_asbplayer_readings"],
            scope["srt_to_ruby_vtt"],
            scope["srt_to_furigana_lines_ass"],
        ) = saved


def test_config_validates_furigana_format():
    bad = '[furigana]\nformat = "srt,mp4"\n'
    with _isolated_config(bad):
        try:
            MODULE["load_user_config"]()
        except MODULE["CliError"] as e:
            assert "mp4" in str(e)
        else:
            raise AssertionError("expected CliError for bad furigana.format")


def test_config_furigana_format_applies_to_download_parser_default():
    toml = '[furigana]\nformat = "srt,ass"\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL"])
    assert args.furigana_format == "srt,ass"


def test_format_flag_and_legacy_alias_both_parse():
    # The canonical flag is --format; --furigana-format is a back-compat
    # alias. Both should land on args.furigana_format.
    with _isolated_config(None):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL", "--format", "srt,ass"])
        assert args.furigana_format == "srt,ass"
        args = parser.parse_args(["URL", "--furigana-format", "all"])
        assert args.furigana_format == "all"
        # And in the modify subcommand.
        modify_parser = MODULE["build_modify_parser"]()
        args = modify_parser.parse_args(["FOLDER", "--furigana", "--format", "srt"])
        assert args.furigana_format == "srt"
        args = modify_parser.parse_args(["FOLDER", "--furigana", "--furigana-format", "srt,vtt"])
        assert args.furigana_format == "srt,vtt"


def test_modify_main_validates_format_upfront_before_progress_bar():
    # A bad --format should fire BEFORE the planning/progress output so the
    # user isn't watching a progress bar that's about to fail.
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Show.S01E01.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
            )
            out = io.StringIO()
            err_caught = None
            with contextlib.redirect_stdout(out):
                try:
                    MODULE["modify_main"]([
                        str(d), "--furigana", "--format", "srt,mp4",
                    ])
                except MODULE["CliError"] as e:
                    err_caught = str(e)
    assert err_caught is not None
    assert "mp4" in err_caught
    # Plan/progress should NOT have been printed.
    text = out.getvalue()
    assert "Planned:" not in text
    assert "Processing:" not in text


# ---------------------------------------------------------------------------
# SAMI (.smi) → SRT conversion
# ---------------------------------------------------------------------------

_SAMI_BASIC_KO = """\
<SAMI>
<HEAD><STYLE TYPE="text/css"><!--
.KRCC {Name: Korean; lang: ko-KR; SAMI_Type: CC;}
--></STYLE></HEAD>
<BODY>
<SYNC Start=1000><P Class=KRCC>안녕하세요<br>반갑습니다</P></SYNC>
<SYNC Start=3500><P Class=KRCC>&nbsp;</P></SYNC>
<SYNC Start=4000><P Class=KRCC>두 번째 줄</P></SYNC>
<SYNC Start=6500><P Class=KRCC>&nbsp;</P></SYNC>
</BODY>
</SAMI>
"""


def test_parse_sami_basic_single_language():
    by_lang = MODULE["parse_sami"](_SAMI_BASIC_KO)
    assert list(by_lang) == ["ko"]
    assert by_lang["ko"] == [
        (1000, 3500, "안녕하세요\n반갑습니다"),
        (4000, 6500, "두 번째 줄"),
    ]


def test_parse_sami_multi_language_emits_one_stream_per_class():
    sami = (
        "<SAMI><BODY>"
        "<SYNC Start=1000><P Class=KRCC>한국어</P><P Class=ENCC>English</P></SYNC>"
        "<SYNC Start=4000><P Class=KRCC>&nbsp;</P><P Class=ENCC>&nbsp;</P></SYNC>"
        "</BODY></SAMI>"
    )
    by_lang = MODULE["parse_sami"](sami)
    assert sorted(by_lang) == ["en", "ko"]
    assert by_lang["ko"] == [(1000, 4000, "한국어")]
    assert by_lang["en"] == [(1000, 4000, "English")]


def test_parse_sami_decodes_entities_and_br_tags():
    sami = (
        "<SAMI><BODY>"
        "<SYNC Start=1000><P Class=KRCC>A &amp; B<br/>line 2 &#65; &#x42;</P></SYNC>"
        "<SYNC Start=3000><P Class=KRCC>&nbsp;</P></SYNC>"
        "</BODY></SAMI>"
    )
    by_lang = MODULE["parse_sami"](sami)
    assert by_lang["ko"] == [(1000, 3000, "A & B\nline 2 A B")]


def test_parse_sami_collapses_multi_br_to_avoid_blank_lines_inside_srt():
    # SAMI files commonly use <br><br> as vertical spacing. If we preserve
    # the empty line, the rendered SRT body contains a blank line, which
    # most SRT readers (and our own parse_srt) treat as a cue separator.
    # Regression: real Dimension W files had 78 cues with this pattern.
    sami = (
        "<SAMI><BODY>"
        "<SYNC Start=1000><P Class=KRCC>윗줄<br><br><br>아랫줄</P></SYNC>"
        "<SYNC Start=4000><P Class=KRCC>&nbsp;</P></SYNC>"
        "</BODY></SAMI>"
    )
    by_lang = MODULE["parse_sami"](sami)
    # Multi-<br> should collapse to a single newline between the two real lines.
    assert by_lang["ko"] == [(1000, 4000, "윗줄\n아랫줄")]
    # And the rendered SRT must parse round-trip with no ghost blocks.
    srt = MODULE["sami_cues_to_srt"](by_lang["ko"])
    cues = MODULE["parse_srt"](srt)
    assert len(cues) == 1, f"expected 1 cue, got {len(cues)}; srt={srt!r}"
    # Body must NOT contain a blank line (would split the cue in two for
    # most SRT readers).
    body_lines = "\n".join(cues[0].text_lines)
    assert "\n\n" not in body_lines
    assert body_lines == "윗줄\n아랫줄"


def test_parse_sami_kokrcc_class_maps_to_ko():
    # Real-world variant seen on Mashle .smi files.
    sami = (
        "<SAMI><BODY>"
        "<SYNC Start=1000><P Class=KOKRCC>한국어</P></SYNC>"
        "<SYNC Start=3000><P Class=KOKRCC>&nbsp;</P></SYNC>"
        "</BODY></SAMI>"
    )
    by_lang = MODULE["parse_sami"](sami)
    assert list(by_lang) == ["ko"]
    assert by_lang["ko"] == [(1000, 3000, "한국어")]


def test_parse_sami_unknown_class_defaults_to_ko():
    sami = (
        "<SAMI><BODY>"
        "<SYNC Start=1000><P Class=WEIRDCC>unrecognised class</P></SYNC>"
        "<SYNC Start=3000><P Class=WEIRDCC>&nbsp;</P></SYNC>"
        "</BODY></SAMI>"
    )
    by_lang = MODULE["parse_sami"](sami)
    # Korean SMI files in the wild use many bespoke class names; default to ko.
    assert list(by_lang) == ["ko"]


def test_parse_sami_handles_missing_p_tag():
    sami = (
        "<SAMI><BODY>"
        "<SYNC Start=1000>그냥 텍스트</SYNC>"
        "<SYNC Start=3000>&nbsp;</SYNC>"
        "</BODY></SAMI>"
    )
    by_lang = MODULE["parse_sami"](sami)
    assert by_lang["ko"] == [(1000, 3000, "그냥 텍스트")]


def test_parse_sami_trailing_cue_gets_three_second_fallback():
    sami = (
        "<SAMI><BODY>"
        "<SYNC Start=1000><P Class=KRCC>마지막 자막</P></SYNC>"
        "</BODY></SAMI>"
    )
    by_lang = MODULE["parse_sami"](sami)
    # No closing SYNC, so duration falls back to 3 seconds.
    assert by_lang["ko"] == [(1000, 4000, "마지막 자막")]


def test_parse_sami_quoted_attribute_values():
    sami = (
        "<SAMI><BODY>"
        '<SYNC Start="1000"><P Class="KRCC">따옴표</P></SYNC>'
        '<SYNC Start="3000"><P Class="KRCC">&nbsp;</P></SYNC>'
        "</BODY></SAMI>"
    )
    by_lang = MODULE["parse_sami"](sami)
    assert by_lang["ko"] == [(1000, 3000, "따옴표")]


def test_parse_sami_returns_empty_for_no_syncs():
    assert MODULE["parse_sami"]("") == {}
    assert MODULE["parse_sami"]("<SAMI><BODY>nothing here</BODY></SAMI>") == {}


def test_sami_cues_to_srt_format_and_fallback_duration():
    srt = MODULE["sami_cues_to_srt"]([(0, 0, "zero-length"), (1000, 2500, "abc")])
    # Zero-length cue should be padded to 1 second.
    assert "00:00:00,000 --> 00:00:01,000" in srt
    assert "00:00:01,000 --> 00:00:02,500" in srt
    # SRT indices are 1-based and contiguous.
    assert srt.startswith("1\n")
    assert "\n\n2\n" in srt


def test_sami_decode_bytes_handles_utf8_cp949_and_utf16_bom():
    text = "<SAMI><BODY><SYNC Start=1000><P Class=KRCC>한국어</P></SYNC></BODY></SAMI>"
    dec = MODULE["_sami_decode_bytes"]
    assert "한국어" in dec(text.encode("utf-8"))
    assert "한국어" in dec(b"\xef\xbb\xbf" + text.encode("utf-8"))   # UTF-8 BOM
    assert "한국어" in dec(text.encode("cp949"))
    assert "한국어" in dec(b"\xff\xfe" + text.encode("utf-16-le"))    # UTF-16 LE BOM


def test_scan_smi_files_is_case_insensitive_and_dedupes():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "a.smi").write_text("x", encoding="utf-8")
        (root / "b.SMI").write_text("x", encoding="utf-8")
        (root / "c.txt").write_text("x", encoding="utf-8")  # ignored
        sub = root / "sub"
        sub.mkdir()
        (sub / "d.smi").write_text("x", encoding="utf-8")
        found = MODULE["scan_smi_files"]([root])
    names = sorted(p.name for p in found)
    assert names == ["a.smi", "b.SMI", "d.smi"]


def test_convert_smi_file_writes_sibling_srt():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        smi = Path(d) / "Show.S01E01.smi"
        smi.write_text(_SAMI_BASIC_KO, encoding="utf-8")
        written, skipped = MODULE["convert_smi_file"](smi)
        assert skipped == []
        assert len(written) == 1
        out = written[0]
        assert out.name == "Show.S01E01.ko.srt"
        body = out.read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:03,500" in body
    assert "안녕하세요" in body and "반갑습니다" in body
    assert "00:00:04,000 --> 00:00:06,500" in body


def test_convert_smi_file_skips_existing_output_without_force():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        smi = Path(d) / "Show.S01E01.smi"
        smi.write_text(_SAMI_BASIC_KO, encoding="utf-8")
        target = Path(d) / "Show.S01E01.ko.srt"
        target.write_text("PRE-EXISTING\n", encoding="utf-8")

        written, skipped = MODULE["convert_smi_file"](smi)
        assert written == []
        assert skipped == [target]
        # Existing file is untouched.
        assert target.read_text(encoding="utf-8") == "PRE-EXISTING\n"

        # --force overwrites.
        written, skipped = MODULE["convert_smi_file"](smi, force=True)
        assert skipped == []
        assert written == [target]
        assert "안녕하세요" in target.read_text(encoding="utf-8")


def test_convert_smi_file_raises_on_unparseable_sami():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        smi = Path(d) / "empty.smi"
        smi.write_text("<SAMI><BODY></BODY></SAMI>", encoding="utf-8")
        err = None
        try:
            MODULE["convert_smi_file"](smi)
        except MODULE["CliError"] as e:
            err = str(e)
    assert err is not None and "no parseable SAMI cues" in err


def test_smi_output_stem_strips_known_lang_infix():
    from pathlib import Path
    stem = MODULE["_smi_output_stem"]
    # Plain stem unchanged.
    assert stem(Path("Show.S01E01.smi")).name == "Show.S01E01"
    # Known lang infix stripped so we don't get Show.ko.ko.srt.
    assert stem(Path("Show.S01E01.ko.smi")).name == "Show.S01E01"
    assert stem(Path("Show.S01E01.en.smi")).name == "Show.S01E01"
    # Non-language tokens preserved.
    assert stem(Path("Show.S01E01.WEB-DL.smi")).name == "Show.S01E01.WEB-DL"
    assert stem(Path("Show.S01E01.x264.smi")).name == "Show.S01E01.x264"


def test_modify_main_convert_smi_to_srt_end_to_end():
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Show.S01E01.smi").write_bytes(_SAMI_BASIC_KO.encode("cp949"))
            (root / "Show.S01E02.smi").write_bytes(_SAMI_BASIC_KO.encode("utf-8"))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["modify_main"]([str(root), "--convert", "smi-to-srt"])
            text = out.getvalue()
            ko1 = (root / "Show.S01E01.ko.srt").read_text(encoding="utf-8")
            ko2 = (root / "Show.S01E02.ko.srt").read_text(encoding="utf-8")
    assert rc == 0
    assert (root.name)  # path was usable during the with-block
    assert "SRT files written from SMI: 2" in text
    assert "안녕하세요" in ko1 and "안녕하세요" in ko2
    assert "00:00:01,000 --> 00:00:03,500" in ko1


def test_modify_main_convert_smi_dry_run_writes_nothing():
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Show.S01E01.smi").write_text(_SAMI_BASIC_KO, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["modify_main"]([
                    str(root), "--convert", "smi-to-srt", "--dry-run",
                ])
            text = out.getvalue()
            srt_exists = (root / "Show.S01E01.ko.srt").exists()
    assert rc == 0
    assert "Planned convert: 1 .smi file(s)" in text
    assert not srt_exists


def test_modify_main_convert_smi_no_files_reports_nothing_to_convert():
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["modify_main"]([d, "--convert", "smi-to-srt"])
            text = out.getvalue()
    assert rc == 1
    assert "No .smi files found" in text


def test_modify_main_convert_combined_with_strip_cc_noise():
    # Both ops can run in one invocation. Convert produces .ko.srt; strip
    # touches any pre-existing .ja.srt with arrows.
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Show.S01E01.smi").write_text(_SAMI_BASIC_KO, encoding="utf-8")
            (root / "Show.S01E01.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nこんにちは➡\n",
                encoding="utf-8",
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["modify_main"]([
                    str(root), "--convert", "smi-to-srt", "--strip-cc-noise",
                ])
            text = out.getvalue()
            ja_body = (root / "Show.S01E01.ja.srt").read_text(encoding="utf-8")
            ko_body = (root / "Show.S01E01.ko.srt").read_text(encoding="utf-8")
    assert rc == 0
    assert "convert smi → srt" in text and "strip CC noise" in text
    assert "➡" not in ja_body
    assert "안녕하세요" in ko_body


def test_modify_main_convert_skips_existing_without_force_via_cli():
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Show.S01E01.smi").write_text(_SAMI_BASIC_KO, encoding="utf-8")
            (root / "Show.S01E01.ko.srt").write_text("HUMAN\n", encoding="utf-8")

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["modify_main"]([str(root), "--convert", "smi-to-srt"])
            text_skip = out.getvalue()
            still_human = (root / "Show.S01E01.ko.srt").read_text(encoding="utf-8")

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc2 = MODULE["modify_main"]([
                    str(root), "--convert", "smi-to-srt", "--force",
                ])
            text_force = out.getvalue()
            forced = (root / "Show.S01E01.ko.srt").read_text(encoding="utf-8")
    assert rc == 0 and rc2 == 0
    assert "SRT files written from SMI: 0 (1 skipped" in text_skip
    assert still_human == "HUMAN\n"
    assert "SRT files written from SMI: 1" in text_force
    assert "안녕하세요" in forced


def test_translator_setup_help_messages_are_specific():
    # Each engine should give an actionable setup hint with at least one
    # concrete command and the engine name.
    argos = MODULE["ArgosTranslator"]()
    ollama = MODULE["OllamaTranslator"]()
    deepl = MODULE["DeepLTranslator"](api_key=None)
    # Argos should reference pip + the English-pivot packages most non-English
    # pairs need.
    msg = argos.setup_help("ja", "ko")
    assert "pip install argostranslate" in msg
    assert "argospm install translate-ja_en" in msg
    assert "argospm install translate-en_ko" in msg
    # Ollama should reference the daemon command + model pull.
    msg = ollama.setup_help()
    assert "ollama serve" in msg and "ollama pull" in msg
    # DeepL should reference the key setup command.
    msg = deepl.setup_help()
    assert "--set-key deepl" in msg or "DEEPL_API_KEY" in msg


def test_deepl_translator_uses_header_auth_not_form_body():
    import json
    import urllib.parse

    captured = {}

    class _Response:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return json.dumps({"translations": [{"text": "안녕하세요"}]}).encode("utf-8")

    def fake_urlopen(req, timeout=30):
        captured["authorization"] = req.get_header("Authorization")
        captured["body"] = req.data.decode("utf-8")
        return _Response()

    urllib_mod = MODULE["urllib"]
    saved_urlopen = urllib_mod.request.urlopen
    try:
        urllib_mod.request.urlopen = fake_urlopen
        out = MODULE["DeepLTranslator"]("test-key").translate_batch(["こんにちは"], "ja", "ko")
    finally:
        urllib_mod.request.urlopen = saved_urlopen

    assert out == ["안녕하세요"]
    assert captured["authorization"] == "DeepL-Auth-Key test-key"
    params = urllib.parse.parse_qs(captured["body"])
    assert "auth_key" not in params
    assert params["source_lang"] == ["JA"]
    assert params["target_lang"] == ["KO"]
    assert params["text"] == ["こんにちは"]


def test_ollama_missing_model_is_pulled_before_translate():
    import json

    calls = []

    class _Response:
        def __init__(self, payload):
            self.payload = payload
            if isinstance(payload, list):
                self.lines = [json.dumps(item).encode("utf-8") + b"\n" for item in payload]
            else:
                self.lines = []
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return json.dumps(self.payload).encode("utf-8")
        def readline(self):
            return self.lines.pop(0) if self.lines else b""

    def fake_urlopen(req, timeout=120):
        calls.append(req.full_url)
        if req.full_url.endswith("/api/tags"):
            return _Response({"models": []})
        if req.full_url.endswith("/api/pull"):
            payload = json.loads(req.data.decode("utf-8"))
            assert payload == {"name": "aya-expanse:8b", "stream": True}
            return _Response([
                {"status": "pulling manifest"},
                {"status": "pulling layer", "completed": 25, "total": 100},
                {"status": "pulling layer", "completed": 100, "total": 100},
                {"status": "success"},
            ])
        if req.full_url.endswith("/api/generate"):
            payload = json.loads(req.data.decode("utf-8"))
            assert payload["model"] == "aya-expanse:8b"
            return _Response({"response": "1. 안녕하세요"})
        raise AssertionError(f"unexpected URL {req.full_url}")

    urllib_mod = MODULE["urllib"]
    saved_urlopen = urllib_mod.request.urlopen
    try:
        urllib_mod.request.urlopen = fake_urlopen
        out = MODULE["OllamaTranslator"](model="aya-expanse:8b").translate_batch(["こんにちは"], "ja", "ko")
    finally:
        urllib_mod.request.urlopen = saved_urlopen

    assert out == ["안녕하세요"]
    assert any(url.endswith("/api/pull") for url in calls)
    assert any(url.endswith("/api/generate") for url in calls)


def test_ollama_pull_failure_gives_model_install_hint():
    import io
    import urllib.error

    class _Response:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return b'{"models":[]}'

    def fake_urlopen(req, timeout=120):
        url = req.full_url
        if url.endswith("/api/tags"):
            return _Response()
        if url.endswith("/api/pull"):
            raise urllib.error.HTTPError(
                url,
                404,
                "Not Found",
                {},
                io.BytesIO(b'{"error":"model not found, try pulling it first"}'),
            )
        raise urllib.error.HTTPError(
            url,
            404,
            "Not Found",
            {},
            io.BytesIO(b'{"error":"model not found, try pulling it first"}'),
        )

    urllib_mod = MODULE["urllib"]
    saved_urlopen = urllib_mod.request.urlopen
    try:
        urllib_mod.request.urlopen = fake_urlopen
        try:
            MODULE["OllamaTranslator"](model="aya-expanse:8b").translate_batch(["こんにちは"], "ja", "ko")
        except MODULE["TranslatorError"] as e:
            msg = str(e)
        else:
            raise AssertionError("expected TranslatorError")
    finally:
        urllib_mod.request.urlopen = saved_urlopen

    assert "Could not pull Ollama model" in msg
    assert "ollama list" in msg
    assert "ollama pull aya-expanse:8b" in msg
    assert "--mt-model NAME" in msg
    assert "model not found" in msg


def test_translate_main_fails_fast_when_engine_not_available():
    # Replace ArgosTranslator with one that always reports unavailable so
    # the pre-flight kicks in. Verify the error is raised ONCE with the
    # install hint, not N times in a per-task loop.
    import tempfile
    from pathlib import Path

    class _UnavailableTranslator(MODULE["_BaseTranslator"]):
        name = "argos"
        def is_available(self):
            return False
        def setup_help(self, source_lang=None, target_lang=None):
            return f"INSTALL_ME: pair={source_lang}_{target_lang}"
        def translate_batch(self, texts, source, target):
            raise AssertionError("translate_batch must not be called when engine is unavailable")

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        scope["select_translator"] = lambda engine, model: _UnavailableTranslator()
        with _isolated_config(None):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                # 5 episodes, all needing ja->ko MT
                for ep in range(1, 6):
                    (root / f"Show.S01E0{ep}.ja.srt").write_text(
                        "1\n00:00:01,000 --> 00:00:02,000\nJ\n", encoding="utf-8"
                    )
                try:
                    MODULE["translate_main"]([
                        str(root), "-l", "ja,ko", "--mt-engine", "argos",
                    ])
                except MODULE["CliError"] as e:
                    # Pre-flight error should:
                    # (a) name the engine,
                    # (b) carry the engine's setup_help text,
                    # (c) include the specific source/target pair hint
                    msg = str(e)
                    assert "argos" in msg
                    assert "INSTALL_ME" in msg
                    assert "ja_ko" in msg
                else:
                    raise AssertionError("expected CliError pre-flight on unavailable engine")
    finally:
        scope["select_translator"] = saved_select


def test_translate_main_groups_identical_per_task_failures():
    # When the engine IS available but per-task calls all fail with the same
    # error (e.g. missing language pair), the summary should show that error
    # ONCE with the count, not N times.
    import tempfile, io, contextlib
    from pathlib import Path

    class _AvailableButFailing(MODULE["_BaseTranslator"]):
        name = "argos"
        def is_available(self):
            return True
        def setup_help(self, source_lang=None, target_lang=None):
            return ""
        def translate_batch(self, texts, source, target):
            raise MODULE["TranslatorError"](
                f"Argos has no installed translation for {source} -> {target}. "
                f"Run: argospm install translate-{source}_{target}"
            )

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        scope["select_translator"] = lambda engine, model: _AvailableButFailing()
        with _isolated_config(None):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                for ep in range(1, 8):
                    (root / f"Show.S01E0{ep}.ja.srt").write_text(
                        "1\n00:00:01,000 --> 00:00:02,000\nJ\n", encoding="utf-8"
                    )
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = MODULE["translate_main"]([
                        str(root), "-l", "ja,ko", "--mt-engine", "argos",
                    ])
                text = out.getvalue()
    finally:
        scope["select_translator"] = saved_select

    assert rc == 1  # nothing written
    # Failure block should show the count and the dedupe header.
    assert "Failures (7)" in text
    assert "7 task(s) failed with the same error" in text
    # Truncates the list of affected tasks to 5 with a "...and N more" line.
    assert "... and 2 more" in text


def test_translate_main_dispatches_via_main():
    # The top-level main() should route 'translate' to translate_main.
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out), _isolated_config(None):
        rc = MODULE["main"](["translate", "--help"])
    assert rc == 0
    assert "Machine-translate" in out.getvalue()


def test_translate_no_args_shows_topic_help():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out), _isolated_config(None):
        rc = MODULE["main"](["translate"])
    assert rc == 0
    assert "Machine-translate" in out.getvalue()


def test_translate_topic_help_covers_both_modes():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out), _isolated_config(None):
        MODULE["main"](["--help", "translate"])
    text = out.getvalue()
    # Documents the standalone subcommand AND the in-download fallback.
    assert "getsubtitle translate PATH" in text
    assert "Inside a download" in text or "URL -l" in text


def test_main_help_lists_translate_subcommand():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out), _isolated_config(None):
        MODULE["main"](["--help"])
    text = out.getvalue()
    assert "translate PATH" in text


def test_dispatch_routes_combine_subcommand():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E07.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
        )
        (root / "Show.S01E07.ko.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n안녕\n", encoding="utf-8"
        )
        # main(['combine', ...]) should dispatch to combine_main.
        rc = MODULE["main"](["combine", str(root), "-l", "ja,ko", "--dry-run"])
        assert rc == 0


def test_existing_download_main_still_parses_url_args():
    # Make sure adding the combine dispatch didn't break the legacy
    # 'getsubtitle URL ...' shape: the parser should still recognise the URL
    # as the positional and not be confused by the new subcommand.
    parser = MODULE["build_parser"]()
    args = parser.parse_args(["https://www.imdb.com/title/tt0245429/", "-l", "ja,ko"])
    assert args.url == "https://www.imdb.com/title/tt0245429/"
    assert args.langs == "ja,ko"


def test_srt_round_trip_preserves_cues():
    src = (
        "1\n"
        "00:00:01,000 --> 00:00:02,000\n"
        "Line A\n"
        "Line B\n"
        "\n"
        "2\n"
        "00:00:03,000 --> 00:00:04,000\n"
        "Single line\n"
    )
    cues = MODULE["parse_srt"](src)
    assert len(cues) == 2
    assert cues[0].index == "1"
    assert cues[0].text_lines == ["Line A", "Line B"]
    assert cues[1].index == "2"
    out = MODULE["serialize_srt"](cues)
    # Round-trip is value-equal modulo trailing whitespace.
    cues2 = MODULE["parse_srt"](out)
    assert [(c.index, c.time_line, c.text_lines) for c in cues] == [
        (c.index, c.time_line, c.text_lines) for c in cues2
    ]


def test_parse_srt_assigns_index_when_missing():
    src = "00:00:01,000 --> 00:00:02,000\nno-index cue\n"
    cues = MODULE["parse_srt"](src)
    assert len(cues) == 1 and cues[0].index == "1"


def test_pick_mt_source_prefers_ja_for_ko():
    from pathlib import Path
    available = {
        "ja": Path("show.ja.srt"),
        "en": Path("show.en.srt"),
    }
    src, path = MODULE["pick_mt_source"]("ko", available)
    assert src == "ja" and path.name == "show.ja.srt"


def test_pick_mt_source_falls_back_to_en():
    from pathlib import Path
    # No ja available -> fall back to en per the priority list.
    available = {"en": Path("show.en.srt")}
    src, path = MODULE["pick_mt_source"]("ko", available)
    assert src == "en"


def test_pick_mt_source_prefers_en_for_es():
    from pathlib import Path
    available = {
        "ja": Path("show.ja.srt"),
        "en": Path("show.en.srt"),
    }
    src, path = MODULE["pick_mt_source"]("es", available)
    assert src == "en"


def test_pick_mt_source_returns_none_when_only_target_available():
    from pathlib import Path
    assert MODULE["pick_mt_source"]("ko", {"ko": Path("show.ko.srt")}) is None
    assert MODULE["pick_mt_source"]("ko", {}) is None


def test_mt_output_path_replaces_lang_token():
    from pathlib import Path
    out = MODULE["mt_output_path"](Path("/tmp/MF Ghost - S01E10.ja.srt"), "ko")
    assert out.name == "MF Ghost - S01E10.ko.mt.srt"
    # Also for English source.
    out = MODULE["mt_output_path"](Path("/tmp/Show - S02E03.en.srt"), "es")
    assert out.name == "Show - S02E03.es.mt.srt"


def test_find_existing_srts_for_episode_groups_by_lang():
    from pathlib import Path
    saved = [
        Path("/tmp/Show - S01E10.ja.srt"),
        Path("/tmp/Show - S01E10.en.srt"),
        Path("/tmp/Show - S01E11.ja.srt"),
        Path("/tmp/Show - S01E10.es.mt.srt"),  # MT files must be excluded
    ]
    out = MODULE["find_existing_srts_for_episode"](saved, "10")
    assert set(out.keys()) == {"ja", "en"}
    assert out["ja"].name == "Show - S01E10.ja.srt"


def test_parse_ollama_numbered_response_basic():
    response = "1. 안녕하세요\n2. 세상\n3. 끝.\n"
    out = MODULE["parse_ollama_numbered_response"](response, 3)
    assert out == ["안녕하세요", "세상", "끝."]


def test_parse_ollama_numbered_response_tolerates_chatter():
    response = (
        "Sure, here are the translations:\n"
        "1) 안녕하세요\n"
        "2) 세상\n"
        "Hope this helps!\n"
    )
    out = MODULE["parse_ollama_numbered_response"](response, 2)
    assert out == ["안녕하세요", "세상"]


def test_parse_ollama_numbered_response_missing_lines_become_empty():
    # Model dropped line 2; the slot should be empty so the caller can fall
    # back to the source text.
    response = "1. ok\n3. third\n"
    out = MODULE["parse_ollama_numbered_response"](response, 3)
    assert out == ["ok", "", "third"]


def test_translate_srt_file_round_trip_with_fake_translator():
    import tempfile
    from pathlib import Path

    class FakeTranslator(MODULE["_BaseTranslator"]):
        name = "fake"
        def is_available(self):
            return True
        def translate_batch(self, texts, source, target):
            # Predictable transform we can assert on.
            return [f"[{target}] {t}" for t in texts]

    src_text = (
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n"
        "\n"
        "2\n00:00:03,000 --> 00:00:04,000\nLine A\nLine B\n"
    )
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "Show.en.srt"
        src.write_text(src_text, encoding="utf-8")
        target = MODULE["mt_output_path"](src, "es")
        count = MODULE["translate_srt_file"](src, target, FakeTranslator(), "en", "es")
        out = target.read_text(encoding="utf-8")

    assert count == 2
    assert target.name == "Show.es.mt.srt"
    assert "[es] Hello" in out
    # The sentinel-based round-trip restores both physical lines. Note: the
    # fake translator prepends "[es] " once, to the joined payload, so only
    # the first line carries the marker. That's correct sentinel behavior.
    cues = MODULE["parse_srt"](out)
    assert cues[1].text_lines == ["[es] Line A", "Line B"]
    # Timings unchanged.
    assert cues[0].time_line == "00:00:01,000 --> 00:00:02,000"


def test_select_translator_unknown_engine_raises():
    cli_error = MODULE["CliError"]
    try:
        MODULE["select_translator"]("notarealengine", None)
    except cli_error as e:
        assert "Unknown --mt-engine" in str(e)
    else:
        raise AssertionError("expected CliError for unknown engine")


def test_strip_cc_noise_removes_continuation_arrows():
    src = (
        "1\n"
        "00:00:01,000 --> 00:00:02,000\n"
        "フルスロットルで来るなんて…。➡\n"
        "\n"
        "2\n"
        "00:00:03,000 --> 00:00:04,000\n"
        "ＭＦＧオフィシャルの➡\n"
        "\n"
        "3\n"
        "00:00:05,000 --> 00:00:06,000\n"
        "no arrow here\n"
    )
    out = MODULE["strip_cc_noise_text"](src)
    assert "➡" not in out
    # Trailing whitespace the arrow left behind should be tidied.
    assert "なんて…。\n" in out
    assert "ＭＦＧオフィシャルの\n" in out
    # Untouched cue stays exactly the same.
    assert "no arrow here\n" in out
    # Timing lines preserved.
    assert "00:00:01,000 --> 00:00:02,000" in out


def test_strip_cc_noise_text_is_idempotent():
    s = "foo➡\nbar"
    once = MODULE["strip_cc_noise_text"](s)
    twice = MODULE["strip_cc_noise_text"](once)
    assert once == twice == "foo\nbar"


def test_strip_cc_noise_text_no_op_when_clean():
    s = "1\n00:00:01,000 --> 00:00:02,000\nclean cue\n"
    assert MODULE["strip_cc_noise_text"](s) == s


def test_strip_cc_noise_in_place_rewrites_file():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "show.ja.srt"
        path.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nなんて…。➡\n", encoding="utf-8"
        )
        MODULE["strip_cc_noise_in_place"](path)
        out = path.read_text(encoding="utf-8")
    assert "➡" not in out
    assert "なんて…。" in out


def test_strip_cc_arrows_legacy_aliases_still_work():
    # The narrow arrow-specific helpers must continue to exist (and behave
    # identically to the noise umbrella) so any external caller using the
    # old names is not broken by the rename.
    s = "foo➡\nbar"
    assert MODULE["strip_cc_arrows_text"](s) == MODULE["strip_cc_noise_text"](s)


def test_strip_cc_arrows_cli_alias_maps_to_strip_cc_noise():
    # Argparse should accept the deprecated --strip-cc-arrows alias and route
    # it to args.strip_cc_noise (the new dest name).
    parser = MODULE["build_parser"]()
    args = parser.parse_args(["--strip-cc-arrows", "https://example.com"])
    assert args.strip_cc_noise is True
    args = parser.parse_args(["--strip-arrows", "https://example.com"])
    assert args.strip_cc_noise is True
    # The canonical name also works.
    args = parser.parse_args(["--strip-cc-noise", "https://example.com"])
    assert args.strip_cc_noise is True


def test_flatten_srt_in_place_joins_multi_line_cues():
    import tempfile
    from pathlib import Path
    srt = (
        "1\n"
        "00:00:01,000 --> 00:00:02,000\n"
        "（テイラー）《こんな所を\n"
        "フルスロットルで来るなんて…。\n"
        "\n"
        "2\n"
        "00:00:03,000 --> 00:00:04,000\n"
        "single-line cue stays as-is\n"
        "\n"
        "3\n"
        "00:00:05,000 --> 00:00:06,000\n"
        "three\n"
        "stacked\n"
        "lines\n"
    )
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "show.ja.srt"
        path.write_text(srt, encoding="utf-8")
        MODULE["flatten_srt_in_place"](path, separator="　")
        out = path.read_text(encoding="utf-8")
    # Cue 1 should be joined onto one line with a full-width space.
    assert "（テイラー）《こんな所を　フルスロットルで来るなんて…。" in out
    # Cue 2 unchanged.
    assert "single-line cue stays as-is" in out
    # Cue 3 fully joined.
    assert "three　stacked　lines" in out
    # Timing lines preserved verbatim.
    assert "00:00:01,000 --> 00:00:02,000" in out
    assert "00:00:05,000 --> 00:00:06,000" in out


def test_flatten_srt_in_place_is_idempotent():
    import tempfile
    from pathlib import Path
    srt = "1\n00:00:01,000 --> 00:00:02,000\nline a\nline b\n"
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "show.en.srt"
        path.write_text(srt, encoding="utf-8")
        MODULE["flatten_srt_in_place"](path, separator=" ")
        first = path.read_text(encoding="utf-8")
        MODULE["flatten_srt_in_place"](path, separator=" ")
        second = path.read_text(encoding="utf-8")
    assert first == second
    assert "line a line b" in first


def test_flatten_separator_picks_full_width_for_ja():
    from pathlib import Path
    assert MODULE["flatten_separator_for"](Path("Show.ja.srt")) == "　"
    assert MODULE["flatten_separator_for"](Path("Show.ko.srt")) == " "
    assert MODULE["flatten_separator_for"](Path("Show.en.srt")) == " "


def test_addic7ed_show_id_exact_match_wins():
    html = """
    <a href="show/1234" debug="0">MF Ghost</a>
    <a href="show/5678" debug="0">MF Ghost Season 2</a>
    """
    assert MODULE["extract_addic7ed_show_id"](html, "MF Ghost") == 1234


def test_addic7ed_show_id_substring_fallback():
    # No exact match -> substring match.
    html = '<a href="show/4321" debug="0">MF Ghost (2023)</a>'
    assert MODULE["extract_addic7ed_show_id"](html, "MF Ghost") == 4321


def test_addic7ed_show_id_no_match_returns_none():
    assert MODULE["extract_addic7ed_show_id"]("<html></html>", "Whatever") is None


def test_addic7ed_episode_parser_returns_subtitle_files():
    html = """
    <table>
      <tr><td><a class="buttonDownload" href="/original/12345/0">Download</a></td></tr>
      <tr><td><a class="buttonDownload" href="/original/12345/1">Download</a></td></tr>
      <tr><td><a class="moreinfo">Details</a></td></tr>
    </table>
    """
    media = MODULE["MediaInfo"](
        source_url="https://example.com/x", provider="example", title="MF Ghost", season="1",
    )
    subs = MODULE["parse_addic7ed_episode_page"](html, media, "https://www.addic7ed.com/serie/1/1/8/22")
    assert len(subs) == 2
    assert all(s.language == "ko" and s.provider == "addic7ed" for s in subs)
    # Download headers should be set so the actual download will work later.
    assert subs[0].download_headers is not None
    assert subs[0].download_headers["Referer"] == "https://www.addic7ed.com/serie/1/1/8/22"
    assert "Mozilla" in subs[0].download_headers["User-Agent"]
    # URL should be absolute, derived from the relative href.
    assert subs[0].url.startswith("https://www.addic7ed.com/original/")


def test_addic7ed_provider_returns_diagnostic_when_no_show():
    # Provider.files() returns (subs, diagnostic). When no show is found,
    # diagnostic should be a non-empty human-readable string.
    a7_globals = MODULE["Addic7edProvider"].files.__globals__
    saved = a7_globals["urllib"].request.urlopen
    # Make _fetch return an empty results page.

    class FakeResponse:
        def __init__(self, body):
            self.body = body.encode("utf-8")
        def read(self):
            return self.body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=20):
        return FakeResponse("<html>no results</html>")

    try:
        a7_globals["urllib"].request.urlopen = fake_urlopen
        prov = MODULE["Addic7edProvider"](enabled=True)
        media = MODULE["MediaInfo"](
            source_url="x", provider="example", title="Nonexistent Show", season="1",
        )
        subs, diag = prov.files(media, "1")
    finally:
        a7_globals["urllib"].request.urlopen = saved

    assert subs == []
    assert diag and isinstance(diag, str)


def test_addic7ed_provider_tries_title_aliases_until_show_found():
    prov = MODULE["Addic7edProvider"](enabled=True)
    calls = []

    def fake_find_show_id(title):
        calls.append(title)
        return (16498, None) if title == "Attack on Titan" else (None, "no matching show")

    def fake_fetch(url):
        return '<a class="buttonDownload" href="/original/12345/0">Download</a>'

    prov._find_show_id = fake_find_show_id
    prov._fetch = fake_fetch
    media = MODULE["MediaInfo"](
        source_url="x",
        provider="example",
        title="Shingeki no Kyojin",
        title_aliases=["Attack on Titan", "進撃の巨人", "진격의 거인"],
        season="1",
    )
    subs, diag = prov.files(media, "1")
    assert diag is None
    assert len(subs) == 1
    assert calls == ["Shingeki no Kyojin", "Attack on Titan"]


def test_addic7ed_provider_returns_diagnostic_on_http_error():
    import urllib.error
    a7_globals = MODULE["Addic7edProvider"].files.__globals__
    saved = a7_globals["urllib"].request.urlopen

    def fake_urlopen(req, timeout=20):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    try:
        a7_globals["urllib"].request.urlopen = fake_urlopen
        prov = MODULE["Addic7edProvider"](enabled=True)
        media = MODULE["MediaInfo"](
            source_url="x", provider="example", title="Blocked Show", season="1",
        )
        subs, diag = prov.files(media, "1")
    finally:
        a7_globals["urllib"].request.urlopen = saved

    assert subs == []
    # The diagnostic should explicitly mention the HTTP status so the user can
    # distinguish anti-bot blocking from "no match".
    assert diag is not None and "403" in diag


def test_addic7ed_episode_parser_handles_empty_page():
    media = MODULE["MediaInfo"](source_url="x", provider="example", title="X", season="1")
    assert MODULE["parse_addic7ed_episode_page"]("", media, "url") == []
    assert MODULE["parse_addic7ed_episode_page"]("<html>nothing here</html>", media, "url") == []


def test_download_headers_threaded_through_save_subtitle():
    # save_subtitle pulls sub.download_headers and passes them to download_bytes.
    # Mock download_bytes to capture what it receives, since the real network
    # call would fail. This protects the Addic7ed download path from regressing.
    save_globals = MODULE["save_subtitle"].__globals__
    saved_dl = save_globals["download_bytes"]
    received = {}

    def fake_download_bytes(url, headers=None):
        received["url"] = url
        received["headers"] = headers
        return b"1\n00:00:00,000 --> 00:00:01,000\nhi\n"

    try:
        save_globals["download_bytes"] = fake_download_bytes
        import tempfile
        from pathlib import Path
        sub = MODULE["SubtitleFile"](
            provider="addic7ed",
            language="ko",
            name="show.ko.srt",
            url="https://www.addic7ed.com/original/1/0",
            download_headers={"Referer": "https://www.addic7ed.com/x", "User-Agent": "M"},
        )
        media = MODULE["MediaInfo"](source_url="x", provider="example", title="Show", season="1")
        with tempfile.TemporaryDirectory() as d:
            MODULE["save_subtitle"](sub, Path(d), media, "1", "1")
    finally:
        save_globals["download_bytes"] = saved_dl

    assert received["url"].endswith("/original/1/0")
    assert received["headers"] == {"Referer": "https://www.addic7ed.com/x", "User-Agent": "M"}


def test_subdivx_parser_handles_empty_and_garbage():
    assert MODULE["parse_subdivx_response"]({}, _make_media(), "1") == []
    assert MODULE["parse_subdivx_response"]([], _make_media(), "1") == []
    assert MODULE["parse_subdivx_response"]("<html>nothing</html>", _make_media(), "1") == []
    assert MODULE["parse_subdivx_response"](None, _make_media(), "1") == []


def test_bridge_external_ids_to_anilist_uses_mal_id():
    # When mal_id is set we should skip Wikidata and match the Anime-IDs entry
    # directly via its mal_id field.
    fake_anime_ids = {
        "show-a": {"mal_id": 30, "anilist_id": 30},
        "show-b": {"mal_id": 99999, "anilist_id": 99999},
    }
    calls = {"wikidata": 0}

    def fake_request_json(url, **kwargs):
        if "anime_ids.json" in url:
            return fake_anime_ids
        # Any other call (Wikidata, etc.) increments and returns nothing.
        calls["wikidata"] += 1
        return {"results": {"bindings": []}}

    saved = _patch_request_json(fake_request_json)
    try:
        media = MODULE["MediaInfo"](
            source_url="https://myanimelist.net/anime/30/x",
            provider="myanimelist",
            mal_id="30",
        )
        MODULE["bridge_external_ids_to_anilist"](media)
    finally:
        _restore_request_json(saved)

    assert media.anilist_id == 30
    assert calls["wikidata"] == 0, "MAL bridge should not need Wikidata"
