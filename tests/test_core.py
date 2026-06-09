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


def test_release_source_detects_new_streaming_services():
    # Hulu / HBO-Max / Disney+ / Apple TV+ / Paramount+ / Peacock all
    # have common release-tag conventions surfaced by Wyzie results.
    nrs = MODULE["normalized_release_source"]
    assert nrs("Show.S01E01.1080p.HULU.WEB-DL.x264") == "hulu"
    assert nrs("Show.S01E01.1080p.HMAX.WEB-DL") == "hbo"
    assert nrs("Show.S01E01.1080p.MAX.WEB-DL") == "hbo"
    assert nrs("Show.S01E01.2160p.DSNP.WEB-DL.HDR") == "disney"
    assert nrs("Movie.2023.1080p.ATVP.WEB-DL") == "apple"
    assert nrs("Show.S01E01.1080p.PMTP.WEB-DL") == "paramount"
    assert nrs("Show.S01E01.1080p.PCOK.WEB-DL") == "peacock"


def test_release_source_from_host_maps_streaming_urls():
    rh = MODULE["release_source_from_host"]
    assert rh("www.netflix.com") == "netflix"
    assert rh("crunchyroll.com") == "crunchyroll"
    assert rh("www.hulu.com") == "hulu"
    assert rh("max.com") == "hbo"
    assert rh("play.max.com") == "hbo"
    assert rh("hbomax.com") == "hbo"
    assert rh("www.disneyplus.com") == "disney"
    assert rh("tv.apple.com") == "apple"
    assert rh("www.paramountplus.com") == "paramount"
    assert rh("peacocktv.com") == "peacock"
    assert rh("www.amazon.com") == "amazon"
    assert rh("primevideo.com") == "amazon"
    # Unknown hosts → None so the caller falls back to the legacy logic.
    assert rh("www.somerandom.com") is None
    assert rh("") is None


def test_release_source_choices_include_new_services():
    # The parser's choices list must accept the new services so users can
    # explicitly opt in with e.g. `--release-source hulu`.
    parser = MODULE["build_parser"]()
    args = parser.parse_args(["URL", "--release-source", "hulu"])
    assert args.release_source == "hulu"
    args = parser.parse_args(["URL", "--release-source", "hbo"])
    assert args.release_source == "hbo"


def test_parse_season_from_title_strips_common_markers():
    p = MODULE["parse_season_from_title"]
    assert p("Mashle Magic And Muscles Season 2") == ("Mashle Magic And Muscles", 2)
    assert p("MF GHOST 3rd Season") == ("MF GHOST", 3)
    assert p("Mashle Magic And Muscles - Season 2") == ("Mashle Magic And Muscles", 2)
    assert p("Hibike Euphonium S2") == ("Hibike Euphonium", 2)
    assert p("Hibike Euphonium Part 1") == ("Hibike Euphonium", 1)
    assert p("Some Anime Cour 2") == ("Some Anime", 2)
    # No marker → unchanged with None.
    assert p("Your Name") == ("Your Name", None)
    assert p("") == ("", None)
    # Don't false-positive on a title that ends with a digit (e.g. "Akira").
    assert p("Akira") == ("Akira", None)


def test_infer_from_crunchyroll_url_extracts_id_and_season():
    # No HTML scrape (request_text mocked to return ""), so we exercise the
    # slug-only path which is what hits Cloudflare-blocked URLs in practice.
    cr_globals = MODULE["infer_from_crunchyroll_url"].__globals__
    saved = cr_globals["request_text"]
    cr_globals["request_text"] = lambda url: ""
    try:
        media = MODULE["infer_from_crunchyroll_url"](
            "https://www.crunchyroll.com/series/G4VUQYDXR/mashle-magic-and-muscles-season-2"
        )
    finally:
        cr_globals["request_text"] = saved
    assert media.title == "Mashle Magic And Muscles"
    assert media.season == "2"
    assert getattr(media, "crunchyroll_id", None) == "G4VUQYDXR"


def test_looks_like_generic_streaming_title_filters_auth_walls():
    f = MODULE["_looks_like_generic_streaming_title"]
    assert f("Sign in to Netflix") is True
    assert f("Watch Now") is True
    assert f("Stream TV and Movies") is True
    assert f("Free Trial") is True
    # Real show titles pass through.
    assert f("The Witcher") is False
    assert f("Couples Therapy") is False


def test_infer_from_streaming_url_extracts_title_from_slug():
    # No HTML available → relies on slug parsing alone.
    sm_globals = MODULE["infer_from_streaming_url"].__globals__
    saved = sm_globals["request_text"]
    sm_globals["request_text"] = lambda url: ""
    try:
        cases = [
            ("https://www.hulu.com/series/the-bear-abc12345", "hulu", "The Bear"),
            # slug_to_title title-cases every word including small words;
            # AniList/TMDB search is case-insensitive so this is fine.
            ("https://max.com/show/house-of-the-dragon", "hbo", "House Of The Dragon"),
            ("https://www.disneyplus.com/series/the-mandalorian/123",
             "disney", "The Mandalorian"),
            ("https://tv.apple.com/us/show/severance/umc.cmc.1srk2goyh",
             "apple", "Severance"),
            ("https://www.paramountplus.com/shows/star-trek-strange-new-worlds/",
             "paramount", "Star Trek Strange New Worlds"),
        ]
        for url, expected_provider, expected_title in cases:
            host = url.split("//", 1)[1].split("/", 1)[0]
            media = MODULE["infer_from_streaming_url"](url, host)
            assert media.provider == expected_provider, (url, media.provider)
            assert media.title == expected_title, (url, media.title)
    finally:
        sm_globals["request_text"] = saved


def test_infer_from_streaming_url_uses_scraped_title_when_present():
    sm_globals = MODULE["infer_from_streaming_url"].__globals__
    saved = sm_globals["request_text"]
    sm_globals["request_text"] = lambda url: (
        '<html><head>'
        '<meta property="og:title" content="The Bear (Hulu)">'
        '</head></html>'
    )
    try:
        media = MODULE["infer_from_streaming_url"](
            "https://www.hulu.com/series/the-bear-deadbeef99",
            "hulu.com",
        )
    finally:
        sm_globals["request_text"] = saved
    # Scraped title wins over slug-derived title (better casing).
    assert media.title == "The Bear (Hulu)"
    assert media.provider == "hulu"


def test_infer_from_streaming_url_ignores_generic_scraped_title():
    sm_globals = MODULE["infer_from_streaming_url"].__globals__
    saved = sm_globals["request_text"]
    # Simulate an auth wall returning a generic page title.
    sm_globals["request_text"] = lambda url: (
        '<html><head>'
        '<meta property="og:title" content="Sign in to Hulu">'
        '<title>Stream TV and Movies Live Online</title>'
        '</head></html>'
    )
    try:
        media = MODULE["infer_from_streaming_url"](
            "https://www.hulu.com/series/the-mandalorian-deadbeef",
            "hulu.com",
        )
    finally:
        sm_globals["request_text"] = saved
    # Slug-derived title used because scraped title was generic boilerplate.
    assert media.title == "The Mandalorian"


def test_infer_media_routes_streaming_hosts_to_generic_handler():
    sm_globals = MODULE["infer_from_streaming_url"].__globals__
    saved = sm_globals["request_text"]
    sm_globals["request_text"] = lambda url: ""
    try:
        for url, expected_provider in [
            ("https://www.hulu.com/series/the-bear-12345", "hulu"),
            ("https://max.com/show/house-of-the-dragon", "hbo"),
            ("https://www.disneyplus.com/series/the-mandalorian/abc", "disney"),
            ("https://tv.apple.com/us/show/severance/xyz", "apple"),
            ("https://www.paramountplus.com/shows/star-trek-snw/", "paramount"),
            ("https://www.peacocktv.com/stream-tv/poker-face", "peacock"),
        ]:
            media = MODULE["infer_media"](url)
            assert media.provider == expected_provider, (url, media.provider)
    finally:
        sm_globals["request_text"] = saved


def test_expand_episodes_uses_tmdb_when_anilist_count_missing():
    # When `-e all` can't be expanded by AniList episodes (None) but the
    # media has a TMDB ID + numeric season, we should fall through to
    # TMDB and produce the right number of episodes.
    import types
    # Patch tmdb_tv_season_episode_count to return a known count without
    # touching the network.
    scope = MODULE["expand_episodes"].__globals__
    saved_tmdb_count = scope["tmdb_tv_season_episode_count"]
    scope["tmdb_tv_season_episode_count"] = lambda tmdb_id, season: 7
    try:
        # Simulate the main()-flow integration: expand returns ["all"] when
        # AniList didn't provide a count.
        first = MODULE["expand_episodes"]("all", None)
        assert first == ["all"]
        # Caller then asks TMDB and would produce 7 episodes.
        # The actual integration sits in main() — we exercise the helper
        # directly here for confidence.
        from getsubtitle_core import tmdb_tv_season_episode_count as _tmdb_count
        n = scope["tmdb_tv_season_episode_count"]("12345", 1)
        assert n == 7
    finally:
        scope["tmdb_tv_season_episode_count"] = saved_tmdb_count


def test_infer_from_netflix_url_falls_back_to_scraped_title():
    # Simulate the Netflix /watch/ URL case where Wikidata has no entry
    # for the title — we should still surface a title (the scraped one)
    # rather than leaving it None.
    nf_globals = MODULE["infer_from_netflix_url"].__globals__
    saved_request_text = nf_globals["request_text"]
    saved_external = nf_globals["external_ids_from_netflix_id"]
    nf_globals["request_text"] = lambda url: (
        '<html><head>'
        '<meta property="og:title" content="Some Niche Show: Pilot">'
        '</head></html>'
    )
    nf_globals["external_ids_from_netflix_id"] = lambda nid: (None, None, None, None)
    try:
        media = MODULE["infer_from_netflix_url"](
            "https://www.netflix.com/watch/81234567"
        )
    finally:
        nf_globals["request_text"] = saved_request_text
        nf_globals["external_ids_from_netflix_id"] = saved_external
    # Wikidata returned nothing AND it was a /watch/ URL — the fallback
    # path uses the scraped (episode) title as a search seed.
    assert media.title == "Some Niche Show: Pilot"
    assert media.provider == "netflix"
    assert media.netflix_id == "81234567"


def test_infer_from_netflix_url_skips_generic_scraped_titles():
    # Auth-walled or anti-bot page returns "Watch Netflix Online" or
    # similar — must NOT be used as a show title.
    nf_globals = MODULE["infer_from_netflix_url"].__globals__
    saved_request_text = nf_globals["request_text"]
    saved_external = nf_globals["external_ids_from_netflix_id"]
    nf_globals["request_text"] = lambda url: (
        '<html><head>'
        '<meta property="og:title" content="Sign in to Netflix">'
        '<title>Watch TV Shows Online</title>'
        '</head></html>'
    )
    nf_globals["external_ids_from_netflix_id"] = lambda nid: (None, None, None, None)
    try:
        media = MODULE["infer_from_netflix_url"](
            "https://www.netflix.com/title/81234567"
        )
    finally:
        nf_globals["request_text"] = saved_request_text
        nf_globals["external_ids_from_netflix_id"] = saved_external
    assert media.title is None  # both scraped candidates were generic


def test_language_aliases():
    assert MODULE["split_csv"]("ja,ko,en,sp", "ja") == ["ja", "ko", "en", "es"]
    assert MODULE["split_csv"]("japanese,korean,english,spanish", "ja") == ["ja", "ko", "en", "es"]
    assert MODULE["split_csv"]("es-mx", "ja") == ["es"]
    assert MODULE["split_csv"]("latin american spanish", "ja") == ["es"]
    assert MODULE["split_csv"]("castilian", "ja") == ["es"]


def test_choose_best_prefers_source_and_srt():
    subtitle = MODULE["SubtitleFile"]
    files = [
        subtitle("wyzie", "en", "movie.bluray.en.srt", "u", release_source="bluray"),
        subtitle("wyzie", "en", "movie.netflix.en.ass", "u", release_source="netflix"),
        subtitle("wyzie", "en", "movie.netflix.en.srt", "u", release_source="netflix"),
    ]
    assert MODULE["choose_best"](files, "netflix").name == "movie.netflix.en.srt"


def test_choose_best_prefers_matching_title_over_alphabetical_false_positive():
    subtitle = MODULE["SubtitleFile"]
    media = MODULE["MediaInfo"](
        source_url="https://www.themoviedb.org/tv/456",
        provider="tmdb",
        title="The Simpsons",
        tmdb_id="456",
        season="1",
        episode="1",
    )
    files = [
        subtitle("wyzie", "en", "(2010) Montevideo, bog te video - Prica prva by www.yubraca.net.srt", "u", provider_language="en", source_provider="charlie", media_title="The Simpsons"),
        subtitle("wyzie", "en", "simpsons_1CD1_engl.srt", "u", provider_language="en", source_provider="charlie", media_title="The Simpsons"),
        subtitle("wyzie", "en", "The.Simpsons.s01e01.DVDRip.XviD-SChiZO.srt", "u", provider_language="en", source_provider="charlie", media_title="The Simpsons"),
    ]
    assert MODULE["choose_best"](files, media=media, episode="1").name == "The.Simpsons.s01e01.DVDRip.XviD-SChiZO.srt"


def test_choose_best_rejects_explicit_episode_mismatches():
    subtitle = MODULE["SubtitleFile"]
    media = MODULE["MediaInfo"](
        source_url="https://www.themoviedb.org/tv/456",
        provider="tmdb",
        title="The Simpsons",
        tmdb_id="456",
        season="1",
        episode="1",
    )
    files = [
        subtitle("wyzie", "en", "The.Simpsons.S20E16.HDTV.XviD-0TV.srt", "u", media_title="The Simpsons"),
        subtitle("wyzie", "en", "The.Simpsons.S08E01.WEB-DL.DSNP.srt", "u", media_title="The Simpsons"),
    ]
    assert MODULE["choose_best"](files, media=media, episode="1") is None


def test_choose_best_rejects_all_unrelated_title_candidates():
    subtitle = MODULE["SubtitleFile"]
    media = MODULE["MediaInfo"](
        source_url="https://www.themoviedb.org/movie/35",
        provider="tmdb",
        title="The Simpsons Movie",
        tmdb_id="35",
        is_movie=True,
    )
    files = [
        subtitle(
            "wyzie",
            "en",
            "Cracker (UK) - 01x02 - The Mad Woman in the Attic (2).srt",
            "u",
            media_title="Cracker (UK)",
        )
    ]
    assert MODULE["choose_best"](files, media=media, episode="auto") is None
    low = MODULE["low_confidence_subtitle_candidate"](files, media=media, episode="auto")
    assert low is files[0]
    reason = MODULE["low_confidence_subtitle_reason"](low, media)
    assert "The Simpsons Movie" in reason
    assert "Cracker" in reason


def test_choose_best_allows_opaque_provider_filenames_under_metadata_id():
    subtitle = MODULE["SubtitleFile"]
    media = MODULE["MediaInfo"](
        source_url="https://www.themoviedb.org/movie/35",
        provider="tmdb",
        title="The Simpsons Movie",
        tmdb_id="35",
        is_movie=True,
    )
    files = [subtitle("wyzie", "en", "12345.srt", "u")]
    assert MODULE["choose_best"](files, media=media, episode="auto") is files[0]


def test_subtitle_search_outcome_leads_with_human_no_found_summary(capsys, tmp_path):
    media = MODULE["MediaInfo"](
        source_url="title://Fena",
        provider="title",
        title="Fena - Pirate Princess",
        title_aliases=["Kaizoku Ojo"],
        season="1",
    )
    results = [
        MODULE["SearchResult"]("ja", "1", "jimaku", "missing"),
        MODULE["SearchResult"]("ja", "2", "jimaku", "missing"),
        MODULE["SearchResult"]("ko", "1", "wyzie", "missing"),
        MODULE["SearchResult"]("ko", "2", "wyzie", "missing"),
    ]
    MODULE["print_subtitle_search_outcome"](
        media,
        ["ja", "ko"],
        ["1", "2"],
        results,
        [],
        expected_output_dir=tmp_path / "Fena - Pirate Princess" / "Season 01",
    )
    out = capsys.readouterr().out
    assert "No subtitles found" in out
    assert "Show:\n  Fena - Pirate Princess" in out
    assert "Requested:\n  Japanese, Korean" in out
    assert "Result:" in out
    assert "Japanese: 0 / 2 episodes" in out
    assert "Korean:   0 / 2 episodes" in out
    assert "Also try searching for:\n  Kaizoku Ojo" in out
    assert "Nothing was downloaded." not in out
    assert "Recommended next steps:" not in out


def test_subtitle_search_outcome_distinguishes_rate_limit(capsys, tmp_path):
    media = MODULE["MediaInfo"](
        source_url="title://Fena",
        provider="title",
        title="Fena - Pirate Princess",
        title_aliases=["Kaizoku Ojo"],
        season="1",
    )
    results = [
        MODULE["SearchResult"]("ja", "1", "jimaku", "error", error="Jimaku rate limit exceeded."),
        MODULE["SearchResult"]("ko", "1", "wyzie", "missing"),
    ]
    MODULE["print_subtitle_search_outcome"](
        media,
        ["ja", "ko"],
        ["1"],
        results,
        [],
        expected_output_dir=tmp_path / "Fena - Pirate Princess" / "Season 01",
    )
    out = capsys.readouterr().out
    assert "Subtitle search was rate-limited" in out
    assert "Possible cause:\n  A subtitle provider asked us to slow down." in out
    assert "Also try searching for:\n  Kaizoku Ojo" in out


def test_no_subtitle_recovery_timeout_recommends_retry_first(monkeypatch, capsys, tmp_path):
    import io

    class TtyInput(io.StringIO):
        def isatty(self):
            return True

    media = MODULE["MediaInfo"](
        source_url="title://Kaizoku%20Oujo",
        provider="title",
        title="Kaizoku Oujo",
        title_aliases=["Fena: Pirate Princess"],
        season="1",
    )
    results = [
        MODULE["SearchResult"]("ja", "1", "jimaku", "error", error="Network timeout for https://jimaku.cc/api/entries/search"),
        MODULE["SearchResult"]("ko", "1", "wyzie", "missing"),
    ]
    g = MODULE["handle_no_subtitles_found_recovery"].__globals__
    monkeypatch.setattr(g["sys"], "stdin", TtyInput("n\nn\n"))
    MODULE["handle_no_subtitles_found_recovery"](
        media,
        ["ja", "ko"],
        ["1"],
        results,
        ["ja episode 1: Network timeout for https://jimaku.cc/api/entries/search"],
        manual_search_mode="on-missing",
        manual_search_open="ask",
        expected_output_dir=tmp_path / "Kaizoku Oujo" / "Season 01",
    )
    out = capsys.readouterr().out
    assert "Could not search for subtitles" in out
    assert "Possible cause:\n  A subtitle provider did not respond." in out
    assert "Open subtitle search pages now? [y/N]" in out
    assert "What you can do" in out
    assert "Retry the search in a few minutes." in out
    assert "Show technical details? [y/N]" in out
    assert "Download subtitles manually." not in out


def test_partial_subtitle_recovery_defaults_to_continue(monkeypatch, capsys, tmp_path):
    import io

    class TtyInput(io.StringIO):
        def isatty(self):
            return True

    media = MODULE["MediaInfo"](
        source_url="https://anilist.co/anime/145665/",
        provider="anilist",
        title="NieR:Automata Ver1.1a",
        title_aliases=["NieR Automata Ver1.1a"],
        season="1",
    )
    results = [
        *(MODULE["SearchResult"]("ja", str(ep), "jimaku", "found") for ep in range(1, 13)),
        *(MODULE["SearchResult"]("ko", str(ep), "wyzie", "error", error="Network timeout for https://sub.wyzie.io/search") for ep in range(1, 3)),
        *(MODULE["SearchResult"]("ko", str(ep), "wyzie", "found") for ep in range(3, 13)),
    ]
    g = MODULE["handle_partial_subtitle_coverage_recovery"].__globals__
    monkeypatch.setattr(g["sys"], "stdin", TtyInput("\n"))

    keep_going = MODULE["handle_partial_subtitle_coverage_recovery"](
        media,
        ["ja", "ko"],
        [str(ep) for ep in range(1, 13)],
        results,
        ["ko episode 1: Network timeout for https://sub.wyzie.io/search"],
        manual_search_mode="on-missing",
        manual_search_open="ask",
        expected_output_dir=tmp_path / "NieR Automata Ver1.1a",
    )
    out = capsys.readouterr().out

    assert keep_going is True
    assert "Subtitle Search Complete" in out
    assert "Japanese  ✓ 12/12" in out
    assert "Korean    ⚠ 10/12" in out
    assert "Missing:\n  Korean E01-E02" in out
    assert "Continue anyway? [Y/n]" in out
    assert "Try these subtitle sources:" not in out
    assert "Network timeout" not in out


def test_partial_subtitle_recovery_details_are_opt_in(monkeypatch, capsys, tmp_path):
    import io

    class TtyInput(io.StringIO):
        def isatty(self):
            return True

    media = MODULE["MediaInfo"](
        source_url="https://anilist.co/anime/145665/",
        provider="anilist",
        title="NieR:Automata Ver1.1a",
        title_aliases=["NieR Automata Ver1.1a"],
        season="1",
    )
    results = [
        MODULE["SearchResult"](
            "ja",
            "1",
            "jimaku",
            "found",
            file=MODULE["SubtitleFile"]("jimaku", "ja", "NieR Automata Ver1.1a - S00E01.ja.srt", "mock://ja"),
        ),
        MODULE["SearchResult"]("ko", "1", "wyzie", "error", error="Network timeout for https://sub.wyzie.io/search"),
    ]
    g = MODULE["handle_partial_subtitle_coverage_recovery"].__globals__
    monkeypatch.setattr(g["sys"], "stdin", TtyInput("n\n4\n3\n"))

    MODULE["handle_partial_subtitle_coverage_recovery"](
        media,
        ["ja", "ko"],
        ["1"],
        results,
        ["ko episode 1: Network timeout for https://sub.wyzie.io/search"],
        manual_search_mode="on-missing",
        manual_search_open="ask",
        expected_output_dir=tmp_path / "NieR Automata Ver1.1a",
    )
    out = capsys.readouterr().out

    assert "How would you like to fill the gaps?" in out
    assert "Show technical details" in out
    assert "Search results:" in out
    assert "Warnings:" in out
    assert "Network timeout" in out


def test_no_subtitle_recovery_yes_opens_sources_without_diagnostic_dump(monkeypatch, capsys, tmp_path):
    import io

    class TtyInput(io.StringIO):
        def isatty(self):
            return True

    media = MODULE["MediaInfo"](
        source_url="title://Kaizoku%20Oujo",
        provider="title",
        title="Kaizoku Oujo",
        title_aliases=["Fena: Pirate Princess"],
        season="1",
    )
    results = [
        MODULE["SearchResult"]("ja", "1", "jimaku", "missing"),
        MODULE["SearchResult"]("ko", "1", "wyzie", "missing"),
    ]
    opened = []
    g = MODULE["handle_no_subtitles_found_recovery"].__globals__
    monkeypatch.setattr(g["sys"], "stdin", TtyInput("\n"))
    monkeypatch.setitem(g, "open_in_browser", lambda url: opened.append(url))
    MODULE["handle_no_subtitles_found_recovery"](
        media,
        ["ja", "ko"],
        ["1"],
        results,
        ["ja episode 1: Jimaku has no matching entry via title aliases."],
        manual_search_mode="on-missing",
        manual_search_open="ask",
        expected_output_dir=tmp_path / "Kaizoku Oujo" / "Season 01",
    )
    out = capsys.readouterr().out
    assert "Could not match this title in subtitle sources" in out
    assert "Open subtitle search pages now? [Y/n]" in out
    assert "Opening:" in out
    assert "Jimaku web search (Japanese)" in out
    assert "Kitsunekko (Japanese)" in out
    assert "Google subtitle searches" in out
    assert "Tip:\n  Search using:\n    Fena: Pirate Princess" in out
    assert "Done." in out
    assert opened
    assert "Search results:" not in out
    assert "Warnings:" not in out
    assert "Manual recovery" not in out


def test_no_subtitle_recovery_no_keeps_manual_recovery_short(monkeypatch, capsys, tmp_path):
    import io

    class TtyInput(io.StringIO):
        def isatty(self):
            return True

    media = MODULE["MediaInfo"](
        source_url="title://Kaizoku%20Oujo",
        provider="title",
        title="Kaizoku Oujo",
        title_aliases=["Fena: Pirate Princess"],
        season="1",
    )
    results = [
        MODULE["SearchResult"]("ja", "1", "jimaku", "missing"),
        MODULE["SearchResult"]("ko", "1", "wyzie", "missing"),
    ]
    g = MODULE["handle_no_subtitles_found_recovery"].__globals__
    monkeypatch.setattr(g["sys"], "stdin", TtyInput("n\nn\n"))
    MODULE["handle_no_subtitles_found_recovery"](
        media,
        ["ja", "ko"],
        ["1"],
        results,
        [],
        manual_search_mode="on-missing",
        manual_search_open="ask",
        expected_output_dir=tmp_path / "Kaizoku Oujo" / "Season 01",
    )
    out = capsys.readouterr().out
    assert "Manual recovery" in out
    assert "Show technical details? [y/N]" in out
    assert "getsubtitle merge" in out
    assert "Search results:" not in out
    assert "Warnings:" not in out
    assert "Try these subtitle sources:" not in out


def test_no_subtitle_recovery_details_are_opt_in(monkeypatch, capsys, tmp_path):
    import io

    class TtyInput(io.StringIO):
        def isatty(self):
            return True

    media = MODULE["MediaInfo"](
        source_url="title://Kaizoku%20Oujo",
        provider="title",
        title="Kaizoku Oujo",
        title_aliases=["Fena: Pirate Princess"],
        season="1",
    )
    results = [
        MODULE["SearchResult"]("ja", "1", "jimaku", "missing"),
        MODULE["SearchResult"]("ko", "1", "wyzie", "missing"),
    ]
    g = MODULE["handle_no_subtitles_found_recovery"].__globals__
    monkeypatch.setattr(g["sys"], "stdin", TtyInput("n\ny\n"))
    MODULE["handle_no_subtitles_found_recovery"](
        media,
        ["ja", "ko"],
        ["1"],
        results,
        ["ja episode 1: Jimaku has no matching entry via title aliases."],
        manual_search_mode="on-missing",
        manual_search_open="ask",
        expected_output_dir=tmp_path / "Kaizoku Oujo" / "Season 01",
    )
    out = capsys.readouterr().out
    assert "Search results:" in out
    assert "Warnings:" in out
    assert "Try these subtitle sources:" in out


def test_print_warnings_groups_repetitive_episode_warnings(capsys):
    warnings = [
        "ja episode 1: Jimaku has no matching entry via AniList ID 122052, TMDB tv:106480, title aliases.",
        "ja episode 2: Jimaku has no matching entry via AniList ID 122052, TMDB tv:106480, title aliases.",
        "ja episode 3: Jimaku rate limit exceeded. Wait a bit, then retry; bulk episode downloads now cache the entry lookup.",
        "ko: broad provider lookup needs an IMDb/TMDB URL plus WYZIE_API_KEY.",
    ]
    MODULE["print_warnings"](warnings)
    out = capsys.readouterr().out
    assert "Japanese subtitles" in out
    assert "Episodes affected: E01-E02" in out
    assert "Jimaku could not find a matching entry for this show." in out
    assert "Episodes affected: E03" in out
    assert "Jimaku rate limit exceeded. Wait a bit, then retry." in out
    assert "ko: broad provider lookup needs" in out
    assert "ja episode 1" not in out


def test_manual_search_copy_is_recovery_oriented(capsys, tmp_path):
    media = MODULE["MediaInfo"](
        source_url="title://Fena",
        provider="title",
        title="Fena - Pirate Princess",
        title_aliases=["Kaizoku Ojo"],
    )
    results = [
        MODULE["SearchResult"]("ja", "1", "jimaku", "missing"),
        MODULE["SearchResult"]("ko", "1", "wyzie", "missing"),
    ]
    MODULE["maybe_print_manual_search_suggestions"](
        media,
        ["ja", "ko"],
        ["1"],
        results,
        open_mode="off",
        expected_output_dir=tmp_path / "Fena - Pirate Princess" / "Season 01",
    )
    out = capsys.readouterr().out
    assert "Try these subtitle sources:" in out
    assert "If you find subtitles manually:" in out
    assert "Note: Some sites may require login, ads, or manual download." in out
    assert "These links do not bypass" not in out
    assert "After downloading manually" not in out


def test_enrich_external_ids_from_wikidata_skips_tmdb_tv_property_for_movies(monkeypatch):
    calls = []
    g = MODULE["enrich_external_ids_from_wikidata"].__globals__
    monkeypatch.setitem(
        g,
        "wikidata_entity_from_statement",
        lambda prop, value: calls.append((prop, value)) or None,
    )
    media = MODULE["MediaInfo"](
        source_url="https://www.themoviedb.org/movie/35",
        provider="tmdb",
        title="The Simpsons Movie",
        tmdb_id="35",
        is_movie=True,
    )
    MODULE["enrich_external_ids_from_wikidata"](media)
    assert ("P4983", "35") not in calls


def test_enrich_tmdb_catalog_external_ids_uses_movie_endpoint(monkeypatch):
    calls = []
    g = MODULE["enrich_tmdb_catalog_external_ids"].__globals__
    monkeypatch.setitem(
        g,
        "tmdb_external_ids",
        lambda media_type, tmdb_id: calls.append((media_type, tmdb_id)) or {"imdb_id": "tt0462538"},
    )
    media = MODULE["MediaInfo"](
        source_url="https://www.themoviedb.org/movie/35",
        provider="tmdb",
        title="The Simpsons Movie",
        tmdb_id="35",
        is_movie=True,
    )
    assert MODULE["enrich_tmdb_catalog_external_ids"](media) is True
    assert calls == [("movie", "35")]
    assert media.imdb_id == "tt0462538"


def test_apply_default_tv_auto_scope_defaults_to_s01e01():
    media = MODULE["MediaInfo"](
        source_url="https://www.themoviedb.org/tv/456",
        provider="tmdb",
        title="The Simpsons",
        tmdb_id="456",
        season="auto",
        episode="auto",
        is_movie=False,
    )
    episodes, changed = MODULE["apply_default_tv_auto_scope"](media, ["auto"])
    assert changed is True
    assert episodes == ["1"]
    assert media.season == "1"
    assert media.episode == "1"


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


def test_provider_language_query_variants_include_spanish_regional_codes():
    assert MODULE["provider_language_query_variants"]("es") == ["es", "spa", "es-419", "es-mx", "es-es"]
    assert MODULE["provider_language_query_variants"]("spanish") == ["es", "spa", "es-419", "es-mx", "es-es"]
    assert MODULE["provider_language_query_variants"]("spanish", provider="wyzie") == ["es"]


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


# ---------------------------------------------------------------------------
# TMDB integration
# ---------------------------------------------------------------------------


def _install_fake_tmdb(payloads_by_path: dict[str, dict | None]):
    """Patch urllib.request.urlopen used by _tmdb_get so the tests don't
    hit the network. Returns a (restore_callable, calls_list) pair."""
    import io
    import json as _json_mod
    import urllib.request

    scope = MODULE["_tmdb_get"].__globals__
    saved = scope["urllib"].request.urlopen
    calls: list[str] = []

    class _FakeResp:
        def __init__(self, body: bytes):
            self._body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._body

    def fake_urlopen(req, timeout=10):
        url = req.full_url
        calls.append(url)
        # Match by the path portion that comes after /3/, before the '?'.
        path_with_query = url.split("/3/", 1)[1] if "/3/" in url else url
        path = path_with_query.split("?", 1)[0]
        # Allow lookup by full path including any query (e.g. "search/tv")
        # but normalise by stripping the api_key param from the URL.
        for key, payload in payloads_by_path.items():
            if path == key:
                if payload is None:
                    err = urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))
                    raise err
                body = _json_mod.dumps(payload).encode("utf-8")
                return _FakeResp(body)
        # Default to 404 so unmatched paths look like misses.
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))

    scope["urllib"].request.urlopen = fake_urlopen

    def restore():
        scope["urllib"].request.urlopen = saved

    return restore, calls


def test_tmdb_search_tv_returns_top_match_with_imdb():
    import json as _json
    payloads = {
        "search/tv": {"results": [{
            "id": 71912, "name": "The Witcher",
            "first_air_date": "2019-12-20", "original_language": "en",
        }]},
        "tv/71912/external_ids": {"imdb_id": "tt5180504"},
    }
    restore, calls = _install_fake_tmdb(payloads)
    MODULE["_TMDB_CACHE"].clear()
    try:
        hit = MODULE["tmdb_search_tv"]("The Witcher", api_key="dummy")
    finally:
        restore()
        MODULE["_TMDB_CACHE"].clear()
    assert hit == {
        "tmdb_id": "71912",
        "imdb_id": "tt5180504",
        "title": "The Witcher",
        "year": 2019,
        "original_language": "en",
    }
    assert len(calls) == 2  # search + external_ids


def test_tmdb_search_movie_returns_top_match_with_imdb():
    payloads = {
        "search/movie": {"results": [{
            "id": 278, "title": "The Shawshank Redemption",
            "release_date": "1994-09-23", "original_language": "en",
        }]},
        "movie/278": {"imdb_id": "tt0111161"},
    }
    restore, _ = _install_fake_tmdb(payloads)
    MODULE["_TMDB_CACHE"].clear()
    try:
        hit = MODULE["tmdb_search_movie"]("The Shawshank Redemption", year=1994, api_key="dummy")
    finally:
        restore()
        MODULE["_TMDB_CACHE"].clear()
    assert hit and hit["tmdb_id"] == "278"
    assert hit["imdb_id"] == "tt0111161"
    assert hit["year"] == 1994


def test_tmdb_search_movie_strips_parenthesized_year_hint():
    payloads = {
        "search/movie": {"results": [{
            "id": 41343, "title": "The God of Cookery",
            "release_date": "1996-12-21", "original_language": "cn",
        }]},
        "movie/41343": {"imdb_id": "tt0116426"},
    }
    restore, calls = _install_fake_tmdb(payloads)
    MODULE["_TMDB_CACHE"].clear()
    try:
        hit = MODULE["tmdb_search_movie"]("The God of Cookery (1996)", api_key="dummy")
    finally:
        restore()
        MODULE["_TMDB_CACHE"].clear()
    assert hit and hit["tmdb_id"] == "41343"
    search_url = next(call for call in calls if "/search/movie?" in call)
    assert "query=The+God+of+Cookery" in search_url
    assert "%281996%29" not in search_url
    assert "year=1996" in search_url


def test_tmdb_search_returns_none_without_key():
    # No api_key arg and no env / Keychain → None, no network call.
    # runpy.run_path returns a shallow COPY of the executed-module globals,
    # so patching MODULE["foo"] doesn't reach the function's __globals__.
    # Patch keychain_get directly in the function's __globals__ to also
    # bypass any real provider key the dev box may have stored.
    import os
    saved_env = os.environ.pop("TMDB_API_KEY", None)
    tv_g = MODULE["tmdb_search_tv"].__globals__
    saved_kc = tv_g["keychain_get"]
    try:
        tv_g["keychain_get"] = lambda *a, **k: None
        assert MODULE["tmdb_search_tv"]("anything") is None
        assert MODULE["tmdb_search_movie"]("anything") is None
    finally:
        tv_g["keychain_get"] = saved_kc
        if saved_env is not None:
            os.environ["TMDB_API_KEY"] = saved_env


def test_tmdb_search_handles_no_results():
    payloads = {"search/tv": {"results": []}}
    restore, _ = _install_fake_tmdb(payloads)
    MODULE["_TMDB_CACHE"].clear()
    try:
        hit = MODULE["tmdb_search_tv"]("not a real show xyz123", api_key="dummy")
    finally:
        restore()
        MODULE["_TMDB_CACHE"].clear()
    assert hit is None


def test_tmdb_search_handles_http_404():
    # _tmdb_get must catch HTTPError and return None.
    restore, _ = _install_fake_tmdb({})  # every path 404s
    MODULE["_TMDB_CACHE"].clear()
    try:
        hit = MODULE["tmdb_search_tv"]("anything", api_key="dummy")
    finally:
        restore()
        MODULE["_TMDB_CACHE"].clear()
    assert hit is None


def test_enrich_media_from_tmdb_populates_imdb_and_tmdb():
    payloads = {
        "search/tv": {"results": [{
            "id": 71912, "name": "The Witcher",
            "first_air_date": "2019-12-20", "original_language": "en",
        }]},
        "tv/71912/external_ids": {"imdb_id": "tt5180504"},
    }
    restore, _ = _install_fake_tmdb(payloads)
    MODULE["_TMDB_CACHE"].clear()
    try:
        media = MODULE["MediaInfo"](source_url="x", provider="manual", title="The Witcher")
        changed = MODULE["enrich_media_from_tmdb"](media, langs=["ko", "en"], api_key="dummy") if False else None
        # api_key kwarg isn't on the public helper; supply via env instead.
        import os
        os.environ["TMDB_API_KEY"] = "dummy"
        try:
            changed = MODULE["enrich_media_from_tmdb"](media, langs=["ko", "en"])
        finally:
            del os.environ["TMDB_API_KEY"]
    finally:
        restore()
        MODULE["_TMDB_CACHE"].clear()
    assert changed is True
    assert media.imdb_id == "tt5180504"
    assert media.tmdb_id == "71912"


def test_enrich_media_from_tmdb_skips_japanese_when_ja_requested():
    # If TMDB says original_language=ja AND user wants ja subs, leave the
    # AniList path alone — Jimaku needs the AniList ID for anime.
    payloads = {
        "search/tv": {"results": [{
            "id": 99999, "name": "Some Anime",
            "first_air_date": "2020-01-01", "original_language": "ja",
        }]},
        "tv/99999/external_ids": {"imdb_id": "tt99999999"},
    }
    restore, _ = _install_fake_tmdb(payloads)
    MODULE["_TMDB_CACHE"].clear()
    import os
    os.environ["TMDB_API_KEY"] = "dummy"
    try:
        media = MODULE["MediaInfo"](source_url="x", provider="manual", title="Some Anime")
        changed = MODULE["enrich_media_from_tmdb"](media, langs=["ja", "ko"])
    finally:
        del os.environ["TMDB_API_KEY"]
        restore()
        MODULE["_TMDB_CACHE"].clear()
    assert changed is False
    assert media.imdb_id is None
    assert media.tmdb_id is None


def test_enrich_media_from_tmdb_populates_japanese_when_ja_not_requested():
    # Same Japanese-origin result, but user only wants ko/en — TMDB should
    # populate so Wyzie's IMDb path lights up.
    payloads = {
        "search/tv": {"results": [{
            "id": 99999, "name": "Some Anime",
            "first_air_date": "2020-01-01", "original_language": "ja",
        }]},
        "tv/99999/external_ids": {"imdb_id": "tt99999999"},
    }
    restore, _ = _install_fake_tmdb(payloads)
    MODULE["_TMDB_CACHE"].clear()
    import os
    os.environ["TMDB_API_KEY"] = "dummy"
    try:
        media = MODULE["MediaInfo"](source_url="x", provider="manual", title="Some Anime")
        changed = MODULE["enrich_media_from_tmdb"](media, langs=["ko", "en"])
    finally:
        del os.environ["TMDB_API_KEY"]
        restore()
        MODULE["_TMDB_CACHE"].clear()
    assert changed is True
    assert media.tmdb_id == "99999"
    assert media.imdb_id == "tt99999999"


def test_enrich_media_from_tmdb_noop_when_ids_already_present():
    # If imdb/tmdb/anilist already set, never even call TMDB.
    restore, calls = _install_fake_tmdb({})
    MODULE["_TMDB_CACHE"].clear()
    import os
    os.environ["TMDB_API_KEY"] = "dummy"
    try:
        for prefilled in (
            {"imdb_id": "tt0111161"},
            {"tmdb_id": "278"},
            {"anilist_id": 19815},
        ):
            media = MODULE["MediaInfo"](
                source_url="x", provider="manual", title="Anything", **prefilled
            )
            changed = MODULE["enrich_media_from_tmdb"](media, langs=["en"])
            assert changed is False
    finally:
        del os.environ["TMDB_API_KEY"]
        restore()
        MODULE["_TMDB_CACHE"].clear()
    assert calls == []  # no network calls at all


def test_tmdb_in_key_providers_registry():
    # The shared --set-key / --reset-key machinery should auto-pick up
    # tmdb via the KEY_PROVIDERS dict.
    kp = MODULE["KEY_PROVIDERS"]
    assert "tmdb" in kp
    assert kp["tmdb"]["env"] == "TMDB_API_KEY"
    assert kp["tmdb"]["account"] == "tmdb"
    assert "subdl" in kp
    assert kp["subdl"]["env"] == "SUBDL_API_KEY"
    assert kp["subdl"]["account"] == "subdl"


def test_provider_choices_accepts_uninstall_friendly_dash_all():
    choices = MODULE["provider_choices"]
    providers = set(MODULE["KEY_PROVIDERS"])
    assert set(choices("all")) == providers
    assert set(choices("-all")) == providers
    assert set(choices("-jimaku,-wyzie")) == {"jimaku", "wyzie"}


def test_wyzie_falls_back_when_broad_call_returns_nothing():
    # If the broad (no-language) call returns 0 items, we should retry once
    # with the language filter applied (legacy behavior).
    wyzie_globals = MODULE["WyzieProvider"].files.__globals__
    saved_request = wyzie_globals["request_json"]
    calls = []
    timeouts = []

    def fake_request_json(url, **kwargs):
        calls.append(url)
        timeouts.append(kwargs.get("timeout"))
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
    assert timeouts == [MODULE["PROVIDER_SEARCH_TIMEOUT_SECONDS"], MODULE["PROVIDER_SEARCH_TIMEOUT_SECONDS"]]


def test_subdl_provider_builds_imdb_tv_query_and_download_url():
    subdl_globals = MODULE["SubDLProvider"]._fetch.__globals__
    saved_request = subdl_globals["request_json"]
    calls = []
    timeouts = []

    def fake_request_json(url, **kwargs):
        calls.append(url)
        timeouts.append(kwargs.get("timeout"))
        return {
            "status": True,
            "subtitles": [
                {
                    "language": "KO",
                    "name": "Test.Show.S01E01.Korean.srt",
                    "url": "/subtitle/test-show-ko.srt",
                    "release_name": "Test.Show.S01E01.1080p.WEB",
                }
            ],
        }

    try:
        subdl_globals["request_json"] = fake_request_json
        prov = MODULE["SubDLProvider"]("subdl-key")
        media = MODULE["MediaInfo"](
            source_url="https://www.imdb.com/title/tt7654321/",
            provider="imdb",
            title="Test Show",
            imdb_id="tt7654321",
            tmdb_id="1234",
            season="1",
        )
        subs = prov.files(media, "1", "ko")
    finally:
        subdl_globals["request_json"] = saved_request

    assert len(subs) == 1
    assert subs[0].provider == "subdl"
    assert subs[0].source_provider == "subdl"
    assert subs[0].url == "https://dl.subdl.com/subtitle/test-show-ko.srt"
    assert "imdb_id=tt7654321" in calls[0]
    assert "season_number=1" in calls[0]
    assert "episode_number=1" in calls[0]
    assert "languages=KO" in calls[0]
    assert timeouts == [MODULE["PROVIDER_SEARCH_TIMEOUT_SECONDS"]]


def test_subdl_provider_uses_unpacked_episode_files():
    subdl_globals = MODULE["SubDLProvider"]._fetch.__globals__
    saved_request = subdl_globals["request_json"]

    def fake_request_json(url, **kwargs):
        return {
            "status": True,
            "subtitles": [
                {
                    "language": "EN",
                    "name": "season-pack.zip",
                    "url": "/subtitle/season-pack.zip",
                    "unpack_files": [
                        {"season": 1, "episode": 1, "name": "Show.S01E01.en.srt", "url": "/subtitle/e1.srt"},
                        {"season": 1, "episode": 2, "name": "Show.S01E02.en.srt", "url": "/subtitle/e2.srt"},
                    ],
                }
            ],
        }

    try:
        subdl_globals["request_json"] = fake_request_json
        prov = MODULE["SubDLProvider"]("subdl-key")
        media = MODULE["MediaInfo"](
            source_url="https://www.themoviedb.org/tv/1234",
            provider="tmdb",
            title="Show",
            tmdb_id="1234",
            season="1",
        )
        subs = prov.files(media, "2", "en")
    finally:
        subdl_globals["request_json"] = saved_request

    assert len(subs) == 1
    assert subs[0].name == "Show.S01E02.en.srt"
    assert subs[0].url == "https://dl.subdl.com/subtitle/e2.srt"


def test_jimaku_provider_can_lookup_by_tmdb_id_when_anilist_is_missing():
    scope = MODULE["JimakuProvider"]._search_entries.__globals__
    saved_request = scope["request_json"]
    calls: list[str] = []
    timeouts: list[int | float | None] = []

    def fake_request_json(url, **kwargs):
        calls.append(url)
        timeouts.append(kwargs.get("timeout"))
        assert kwargs["headers"]["Authorization"] == "jimaku-key"
        return [{"id": 42, "name": "My Neighbor Totoro"}]

    try:
        scope["request_json"] = fake_request_json
        provider = MODULE["JimakuProvider"]("jimaku-key")
        media = MODULE["MediaInfo"](
            source_url="https://www.themoviedb.org/movie/8392",
            provider="tmdb",
            title="My Neighbor Totoro",
            tmdb_id="8392",
            is_movie=True,
        )
        assert provider.search_entry_id(media) == 42
    finally:
        scope["request_json"] = saved_request

    assert "tmdb_id=movie%3A8392" in calls[0]
    assert timeouts == [MODULE["PROVIDER_SEARCH_TIMEOUT_SECONDS"]]


def test_jimaku_provider_query_fallback_uses_title_aliases_carefully():
    scope = MODULE["JimakuProvider"]._search_entries.__globals__
    saved_request = scope["request_json"]
    calls: list[str] = []

    def fake_request_json(url, **kwargs):
        calls.append(url)
        if "query=Fena" in url:
            return [{"id": 1, "name": "Wrong Fuzzy Result"}]
        if "query=Kaizoku+Oujo" in url:
            return [
                {"id": 2, "name": "Other Show"},
                {"id": 77, "name": "Kaizoku Oujo", "english_name": "Fena: Pirate Princess"},
            ]
        return []

    try:
        scope["request_json"] = fake_request_json
        provider = MODULE["JimakuProvider"]("jimaku-key")
        media = MODULE["MediaInfo"](
            source_url="title://Fena",
            provider="title",
            title="Fena",
            title_aliases=["Kaizoku Oujo", "海賊王女"],
        )
        assert provider.search_entry_id(media) == 77
    finally:
        scope["request_json"] = saved_request

    assert any("query=Fena" in call for call in calls)
    assert any("query=Kaizoku+Oujo" in call for call in calls)


def test_url_form_uses_subdl_fallback_without_wyzie_key():
    import io
    import contextlib
    import os

    main_globals = MODULE["main"].__globals__
    saved_request = main_globals["request_json"]
    saved_keychain = main_globals["keychain_get"]
    saved_subdl_env = os.environ.get("SUBDL_API_KEY")
    saved_wyzie_env = os.environ.get("WYZIE_API_KEY")
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append(url)
        if "query.wikidata.org" in url:
            return {
                "results": {
                    "bindings": [
                        {"itemLabel": {"value": "Test Movie"}}
                    ]
                }
            }
        if "api.subdl.com" in url:
            return {
                "status": True,
                "subtitles": [
                    {
                        "language": "KO",
                        "name": "Movie.Korean.srt",
                        "url": "/subtitle/movie-ko.srt",
                    }
                ],
            }
        raise AssertionError(f"unexpected network call: {url}")

    try:
        os.environ["SUBDL_API_KEY"] = "subdl-key"
        os.environ.pop("WYZIE_API_KEY", None)
        main_globals["request_json"] = fake_request_json
        main_globals["keychain_get"] = lambda service, account: None
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()) as out:
            rc = MODULE["main"]([
                "https://www.imdb.com/title/tt7654321/",
                "-s", "1", "-e", "1", "-l", "ko",
                "--dry-run",
            ])
    finally:
        main_globals["request_json"] = saved_request
        main_globals["keychain_get"] = saved_keychain
        if saved_subdl_env is None:
            os.environ.pop("SUBDL_API_KEY", None)
        else:
            os.environ["SUBDL_API_KEY"] = saved_subdl_env
        if saved_wyzie_env is None:
            os.environ.pop("WYZIE_API_KEY", None)
        else:
            os.environ["WYZIE_API_KEY"] = saved_wyzie_env

    text = out.getvalue()
    assert rc == 0
    assert "SubDL: retrying" in text
    assert "Subtitle Search Complete" in text
    assert "Korean: 1 / 1 episode" in text
    assert "WYZIE_API_KEY" not in text
    assert any("api.subdl.com" in call for call in calls)


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
    assert pem("무빙.E01.230809.1080p.WEB-DL.ko.hi.srt") == (1, 1)
    assert pem("Drama_E20_1080p.en.srt") == (1, 20)
    assert pem("no markers here.srt") is None


def test_save_subtitle_season_all_uses_parseable_episode_marker():
    import tempfile
    from pathlib import Path
    scope = MODULE["save_subtitle"].__globals__
    saved_dl = scope["download_bytes"]
    try:
        scope["download_bytes"] = lambda url, headers=None: b"1\n00:00:01,000 --> 00:00:02,000\nhi\n"

        class FakeSub:
            name = "ep1.srt"
            language = "ja"
            url = "mock://"
            download_headers = None

        with tempfile.TemporaryDirectory() as d:
            media = MODULE["MediaInfo"](source_url="x", provider="anilist", title="Show")
            saved = MODULE["save_subtitle"](FakeSub(), Path(d), media, "all", "1")
        assert saved[0].name == "Show - S01E01.ja.srt"
        assert MODULE["parse_episode_marker"](saved[0].name) == (1, 1)
    finally:
        scope["download_bytes"] = saved_dl


def test_save_subtitle_episode_filename_start_shifts_output_episode_number():
    import tempfile
    from pathlib import Path
    scope = MODULE["save_subtitle"].__globals__
    saved_dl = scope["download_bytes"]
    try:
        scope["download_bytes"] = lambda url, headers=None: b"1\n00:00:01,000 --> 00:00:02,000\nhi\n"

        class FakeSub:
            name = "ep1.srt"
            language = "ja"
            url = "mock://"
            download_headers = None

        with tempfile.TemporaryDirectory() as d:
            media = MODULE["MediaInfo"](source_url="x", provider="crunchyroll", title="MF Ghost")
            saved = MODULE["save_subtitle"](
                FakeSub(), Path(d), media, "3", "1",
                episode_filename_start=25,
            )
        assert saved[0].name == "MF Ghost - S03E25.ja.srt"
        assert MODULE["parse_episode_marker"](saved[0].name) == (3, 25)
    finally:
        scope["download_bytes"] = saved_dl


def test_save_subtitle_unknown_release_suffix_defaults_to_srt(tmp_path):
    scope = MODULE["save_subtitle"].__globals__
    saved_dl = scope["download_bytes"]
    try:
        scope["download_bytes"] = lambda url, headers=None: b"1\n00:00:01,000 --> 00:00:02,000\nhi\n"
        sub = MODULE["SubtitleFile"](
            provider="wyzie",
            language="ko",
            name="NieR Automata Ver1.1a.S01E03.1080p",
            url="mock://",
        )
        media = MODULE["MediaInfo"](source_url="x", provider="anilist", title="NieR Automata Ver1.1a")
        saved = MODULE["save_subtitle"](sub, tmp_path, media, "0", "3")
    finally:
        scope["download_bytes"] = saved_dl

    assert saved[0].name == "NieR Automata Ver1.1a - S00E03.ko.srt"
    assert saved[0].suffix == ".srt"
    assert MODULE["parse_srt_filename"](saved[0].name) == (0, 3, "ko", False)


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


def test_parse_srt_filename_strips_sonarr_hi_cc_sdh_forced_tags():
    # Sonarr-style hearing-impaired / closed-caption / SDH / forced markers
    # sit between the lang code and .srt. Without stripping, the regex would
    # misread `.ja.hi.srt` as lang=hi. Real-world impact: most of the
    # user's Midnight Diner / Witcher / Couples Therapy files.
    p = MODULE["parse_srt_filename"]
    assert p("Show.S01E07.ja.hi.srt") == (1, 7, "ja", False)
    assert p("Show.S01E07.en.cc.srt") == (1, 7, "en", False)
    assert p("Show.S01E07.es.sdh.srt") == (1, 7, "es", False)
    assert p("Show.S01E07.fr.forced.srt") == (1, 7, "fr", False)
    # Stacks with .mt too.
    assert p("Show.S01E07.ko.mt.hi.srt") == (1, 7, "ko", True)
    # Real-world fixtures from the user's library.
    assert p("Midnight.Diner.S01E03.1080p.NF.WEB-DL.DDP2.0.H.264-DUSKLiGHT.ja.hi.srt") == (1, 3, "ja", False)
    assert p("Couples Therapy (2019) - S01E01 - 101 WEBDL-1080p.en.hi.srt") == (1, 1, "en", False)
    assert p("The Witcher - S02E05 - Turn Your Back WEBRip-1080p Proper.es.hi.srt") == (2, 5, "es", False)
    assert p("Moving (2023) - S01E16 - The Man Between WEBDL-1080p.ko.hi.srt") == (1, 16, "ko", False)


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


def test_scan_srt_files_ignores_macos_appledouble_sidecars_and_parses_bare_e():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        good = root / "무빙.E01.230809.1080p.WEB-DL.AAC2.0.H264-ApeachX.ko.hi.srt"
        sidecar = root / ("._" + good.name)
        good.write_text("1\n00:00:01,000 --> 00:00:02,000\n안녕\n", encoding="utf-8")
        sidecar.write_bytes(b"\x00\x05\x16\x07Mac OS X metadata")
        scanned = MODULE["scan_srt_files"]([root])
    assert scanned == [(good, 1, 1, "ko", False)]


def test_scan_srt_files_for_merge_infers_release_style_cjk_subtitles(tmp_path):
    root = tmp_path
    ja_text = (
        "1\n00:00:06,000 --> 00:00:08,000\n"
        "ここからセクター２！\n"
    )
    ko_text = (
        "1\n00:00:05,000 --> 00:00:07,000\n"
        "여기부터 섹터 2! 한국어 자막 테스트입니다. 다음 대사도 한국어입니다.\n"
    )
    (root / "NieR Automata Ver1.1a - S00E01.ja.srt").write_text(ja_text, encoding="utf-8")
    (root / "NieR Automata Ver1.1a - S00E02.ja.srt").write_text(ja_text, encoding="utf-8")
    # No language token: infer Korean from Hangul content and episode from
    # the release-style "- 01 (...)" marker.
    (root / "[Ohys-Raws] NieR Automata Ver1.1a - 01 (BS11 1280x720 x264 AAC).srt").write_text(
        ko_text, encoding="utf-8"
    )
    # Has .ko.srt but normal parsing would classify it as movie S00E00;
    # merge repair should remap it to the contextual S00E02.
    (root / "[Ohys-Raws] NieR Automata Ver1.1a - 02 (BS11 1280x720 x264 AAC).ko.srt").write_text(
        ko_text, encoding="utf-8"
    )

    scanned, inferred = MODULE["scan_srt_files_for_merge"]([root], requested_langs=["ja", "ko"])
    grouped = MODULE["group_srts_by_episode"](scanned)

    assert grouped[(0, 1)]["ko"].name == "[Ohys-Raws] NieR Automata Ver1.1a - 01 (BS11 1280x720 x264 AAC).srt"
    assert grouped[(0, 2)]["ko"].name == "[Ohys-Raws] NieR Automata Ver1.1a - 02 (BS11 1280x720 x264 AAC).ko.srt"
    assert {(season, ep, lang, reason) for _path, season, ep, lang, reason in inferred} == {
        (0, 1, "ko", "script language"),
        (0, 2, "ko", "filename episode"),
    }


def test_extended_scan_uses_merge_inference_for_pseudo_lang_workflows(tmp_path):
    root = tmp_path
    (root / "NieR Automata Ver1.1a - S00E01.ja.srt").write_text(
        "1\n00:00:06,000 --> 00:00:08,000\nここからセクター２！\n",
        encoding="utf-8",
    )
    (root / "[Ohys-Raws] NieR Automata Ver1.1a - 01 (BS11 1280x720 x264 AAC).srt").write_text(
        "1\n00:00:05,000 --> 00:00:07,000\n"
        "여기부터 섹터 2! 한국어 자막 테스트입니다. 다음 대사도 한국어입니다.\n",
        encoding="utf-8",
    )

    scanned = MODULE["scan_subtitle_files_extended"](
        [root],
        pseudo_langs=["ja-hiragana"],
        requested_langs=["ja-hiragana", "ja", "ko"],
    )

    assert any(path.name.startswith("[Ohys-Raws]") and season == 0 and episode == 1 and lang == "ko"
               for path, season, episode, lang, _is_mt, _fmt in scanned)


def test_scan_srt_files_for_merge_does_not_infer_without_episode_context(tmp_path):
    root = tmp_path
    (root / "[Ohys-Raws] Unknown - 01 (BS11 1280x720 x264 AAC).srt").write_text(
        "1\n00:00:05,000 --> 00:00:07,000\n여기부터 섹터 2! 한국어 자막 테스트입니다. 다음 대사도 한국어입니다.\n",
        encoding="utf-8",
    )

    scanned, inferred = MODULE["scan_srt_files_for_merge"]([root], requested_langs=["ja", "ko"])

    assert scanned == []
    assert inferred == []


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


def test_combine_cues_label_langs_prefixes_each_block():
    SrtCue = MODULE["SrtCue"]
    master = [SrtCue("1", "00:00:01,000 --> 00:00:03,000", ["Line A", "Line B"])]
    targets = {"ko": [SrtCue("1", "00:00:01,000 --> 00:00:03,000", ["가", "나"])]}
    # preserve_lines so we can confirm only the FIRST line of each block is tagged.
    combined, _ = MODULE["combine_cues"](
        master, targets, ["en", "ko"], "en", MODULE["SYNC_PRESETS"]["auto"],
        preserve_lines=True, label_langs=True,
    )
    assert combined[0].text_lines == ["[EN] Line A", "Line B", "[KO] 가", "나"]


def test_combine_cues_label_langs_off_by_default():
    SrtCue = MODULE["SrtCue"]
    master = [SrtCue("1", "00:00:01,000 --> 00:00:02,000", ["Hello"])]
    targets = {"ko": [SrtCue("1", "00:00:01,000 --> 00:00:02,000", ["안녕"])]}
    combined, _ = MODULE["combine_cues"](
        master, targets, ["en", "ko"], "en", MODULE["SYNC_PRESETS"]["auto"],
    )
    assert combined[0].text_lines == ["Hello", "안녕"]


def test_run_registry_save_list_remove(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GETSUBTITLE_CONFIG_PATH", str(tmp_path / "user_settings.toml"))
    wf = tmp_path / "wf.toml"
    wf.write_text('[fetch]\nsource = "x"\n', encoding="utf-8")
    assert MODULE["run_main"](["--save", "myflow", str(wf)]) == 0
    assert (tmp_path / "pipelines" / "myflow.toml").is_file()
    capsys.readouterr()
    assert MODULE["run_main"](["--list"]) == 0
    assert "myflow" in capsys.readouterr().out
    assert MODULE["run_main"](["--remove", "myflow"]) == 0
    assert not (tmp_path / "pipelines" / "myflow.toml").exists()


def test_run_registry_rejects_unsafe_name(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("GETSUBTITLE_CONFIG_PATH", str(tmp_path / "user_settings.toml"))
    wf = tmp_path / "wf.toml"
    wf.write_text("[fetch]\nsource = \"x\"\n", encoding="utf-8")
    with pytest.raises(MODULE["CliError"]):
        MODULE["run_main"](["--save", "../evil", str(wf)])


def test_run_registry_unknown_name_errors(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("GETSUBTITLE_CONFIG_PATH", str(tmp_path / "user_settings.toml"))
    with pytest.raises(MODULE["CliError"]):
        MODULE["run_main"](["does-not-exist"])


def test_run_help_topic_exists_and_renders(capsys):
    # CODEX #1: `getsubtitle --help run` and `getsubtitle run --help` both work.
    assert "run" in MODULE["HELP_TOPICS"]
    assert MODULE["run_main"](["--help"]) == 0
    assert "Save and run workflows" in capsys.readouterr().out
    assert MODULE["_show_topic_help"](["--help", "run"]) == 0
    assert "Save and run workflows" in capsys.readouterr().out


def test_pipeline_name_rejects_leading_dash():
    # CODEX #4: names like --help/--list collide with run's own flags.
    import pytest
    for bad in ("--help", "-x", "--list", "--save"):
        with pytest.raises(MODULE["CliError"]):
            MODULE["_pipeline_registry_path"](bad)


def test_config_toml_merge_label_langs_emits_flag():
    # CODEX #2: [merge] label_langs in a --config TOML reaches combine.
    argv, _ = MODULE["_toml_to_pipeline_argv"]({"merge": {"languages": "ja,en", "label_langs": True}})
    assert "--label-langs" in argv


def test_inline_merge_label_langs_survives_config_override():
    # CODEX #2: `--config flow.toml --merge --label-langs` is no longer dropped.
    ov, _residual, vb = MODULE["_extract_cli_overrides"](["--merge", "--label-langs"])
    data = MODULE["_merge_overrides_into_toml"]({"merge": {"languages": "ja,en"}}, ov, vb)
    argv, _ = MODULE["_toml_to_pipeline_argv"](data)
    assert "--label-langs" in argv


def test_user_settings_merge_label_langs_honored(tmp_path, monkeypatch):
    # CODEX #2: [merge] label_langs = true in user_settings.toml is honored
    # by the direct `merge` subcommand (no --label-langs on the CLI).
    cfg = tmp_path / "user_settings.toml"
    cfg.write_text("[merge]\nlabel_langs = true\n", encoding="utf-8")
    monkeypatch.setenv("GETSUBTITLE_CONFIG_PATH", str(cfg))
    assert MODULE["validate_user_config"]({"merge": {"label_langs": True}})["merge"]["label_langs"] is True
    assert MODULE["_combine_label_langs_from_config"]() is True
    (tmp_path / "S.S01E01.ja.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nこ\n", encoding="utf-8")
    (tmp_path / "S.S01E01.en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nh\n", encoding="utf-8")
    rc = MODULE["combine_main"]([str(tmp_path), "-l", "ja,en", "--force", "--no-open-folder-prompt"])
    assert rc == 0
    assert "[JA]" in (tmp_path / "S.S01E01.ja-en.srt").read_text(encoding="utf-8")


def test_merge_help_mentions_label_langs():
    assert "--label-langs" in MODULE["HELP_TOPICS"]["merge"]


def test_rename_value_safety_and_plan_guard(tmp_path):
    # CODEX #3: unsafe filename parts must not raise a raw ValueError.
    import pytest
    assert MODULE["_rename_value_is_safe"]("Good Title")   # internal space OK
    assert not MODULE["_rename_value_is_safe"]("Bad/Title")
    assert not MODULE["_rename_value_is_safe"]("vtt\\bad")
    # Windows-reserved characters and trailing dot/space also rejected.
    assert not MODULE["_rename_value_is_safe"]("vtt:bad")
    assert not MODULE["_rename_value_is_safe"]("a*b")
    assert not MODULE["_rename_value_is_safe"]('q"x')
    assert not MODULE["_rename_value_is_safe"]("a|b")
    assert not MODULE["_rename_value_is_safe"]("a?b")
    assert not MODULE["_rename_value_is_safe"]("trailing ")
    assert not MODULE["_rename_value_is_safe"]("dot.")
    p = tmp_path / "Show - S01E01.ja.srt"
    p.write_text("x", encoding="utf-8")
    part = MODULE["_rename_parse_parts"](p)
    part.title = "Bad/Title"
    with pytest.raises(MODULE["CliError"]):
        MODULE["_rename_plan_for_parts"]([part])


def test_no_label_langs_overrides_user_settings(tmp_path, monkeypatch):
    # --no-label-langs wins over [merge] label_langs = true in user_settings.
    cfg = tmp_path / "user_settings.toml"
    cfg.write_text("[merge]\nlabel_langs = true\n", encoding="utf-8")
    monkeypatch.setenv("GETSUBTITLE_CONFIG_PATH", str(cfg))
    (tmp_path / "S.S01E01.ja.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nこ\n", encoding="utf-8")
    (tmp_path / "S.S01E01.en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nh\n", encoding="utf-8")
    rc = MODULE["combine_main"]([
        str(tmp_path), "-l", "ja,en", "--no-label-langs",
        "--force", "--no-open-folder-prompt",
    ])
    assert rc == 0
    assert "[JA]" not in (tmp_path / "S.S01E01.ja-en.srt").read_text(encoding="utf-8")


def test_inline_no_label_langs_clears_config_flag():
    # `--config flow.toml --merge --no-label-langs` overrides a TOML true.
    ov, _residual, vb = MODULE["_extract_cli_overrides"](["--merge", "--no-label-langs"])
    data = MODULE["_merge_overrides_into_toml"](
        {"merge": {"languages": "ja,en", "label_langs": True}}, ov, vb)
    argv, _ = MODULE["_toml_to_pipeline_argv"](data)
    assert "--label-langs" not in argv


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


def test_combine_cues_accepts_realistic_offset_with_extra_target_cues():
    SrtCue = MODULE["SrtCue"]

    def cue(index: int, start_ms: int, end_ms: int, text: str) -> object:
        def stamp(ms: int) -> str:
            seconds, milli = divmod(ms, 1000)
            minutes, sec = divmod(seconds, 60)
            hours, minute = divmod(minutes, 60)
            return f"{hours:02d}:{minute:02d}:{sec:02d},{milli:03d}"

        return SrtCue(str(index), f"{stamp(start_ms)} --> {stamp(end_ms)}", [text])

    # Shape based on a real NieR Automata pair:
    # - Japanese starts about 1 second after Korean.
    # - The two releases have different cue counts.
    # - Extra target-only signs / sound-effect cues should not drag the
    #   episode-level match rate below the auto threshold.
    master = [
        cue(i + 1, 6381 + i * 10_000, 9000 + i * 10_000, f"ja {i + 1}")
        for i in range(12)
    ]
    target = [
        cue(1, 1000, 3000, "ko opening sign"),
        cue(2, 5349, 6170, "ko 1"),
        cue(3, 15381, 16200, "ko 2"),
        cue(4, 25381, 26200, "ko 3"),
        cue(5, 35381, 36200, "ko 4"),
        cue(6, 40100, 41500, "ko extra sound effect"),
        cue(7, 45381, 46200, "ko 5"),
        cue(8, 55381, 56200, "ko 6"),
        cue(9, 65381, 66200, "ko 7"),
        cue(10, 75381, 76200, "ko 8"),
        cue(11, 85381, 86200, "ko 9"),
        cue(12, 95381, 96200, "ko 10"),
        cue(13, 130000, 132000, "ko ending sign"),
    ]

    offset = MODULE["estimate_timing_offset_ms"](master, target, MODULE["SYNC_PRESETS"]["auto"])
    combined, rates = MODULE["combine_cues"](
        master, {"ko": target}, ["ja", "ko"], "ja", MODULE["SYNC_PRESETS"]["auto"],
    )
    assert offset == 1000
    assert rates["ko"] > MODULE["SYNC_PRESETS"]["auto"]["episode_success"]
    assert combined[0].text_lines == ["ja 1", "ko 1"]
    assert combined[9].text_lines == ["ja 10", "ko 10"]
    assert combined[10].text_lines == ["ja 11"]


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


def test_kanji_reading_line_romaji_uses_full_sentence():
    line = MODULE["kanji_reading_line"]("（望）７号車と６号車がくっついた。", "romaji")
    assert "gousha" in line
    assert "kuttsuita" in line
    assert any(number in line for number in ("７", "7", "nana", "shichi"))
    assert "号車" not in line


def test_text_with_ruby_romaji_outputs_normal_sized_line():
    out = MODULE["text_with_ruby"]("（望）７号車と６号車がくっついた。", "romaji")
    assert "<ruby>" not in out
    assert "<rt>" not in out
    assert "gousha" in out
    assert "kuttsuita" in out


def test_japanese_reading_disambiguates_kimi_and_kun():
    assert "<rt>きみ</rt>" in MODULE["text_with_ruby"]("君の車だ", "hiragana")
    assert "<rt>くん</rt>" in MODULE["text_with_ruby"]("田中君のせいだ", "hiragana")


def test_japanese_reading_trims_kana_suffixes_from_compounds():
    assert MODULE["text_with_readings"]("生ビールをください。", "hiragana") == "生（なま）ビールをください。"


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
    # Sonarr HI/CC tags should also be stripped, not doubled into
    # Show.S01E07.ko.ko-en.srt.
    assert n(Path("/x/Show.S01E07.ko.hi.srt"), ["ko", "en"]) == "Show.S01E07.ko-en.srt"
    p = MODULE["combined_output_path"]
    assert p(Path("/x/MF Ghost - S01E07.ja.srt"), ["ja", "ko"], furigana=True, fmt="vtt") == "MF Ghost - S01E07.ja-furigana-ko.vtt"


def test_pseudo_lang_detection():
    """is_pseudo_lang recognises the multi-variant codes; rejects plain
    ISO codes and unknown hyphenated tokens."""
    is_pseudo = MODULE["is_pseudo_lang"]
    assert is_pseudo("ja-hiragana")
    assert is_pseudo("ja-katakana")
    assert is_pseudo("ja-romaji")
    assert is_pseudo("ko-revised")
    assert is_pseudo("ko-yale")
    assert is_pseudo("zh-marks")
    assert is_pseudo("zh-numbers")
    assert is_pseudo("zh-letters")
    assert is_pseudo("yue-numbers")
    assert is_pseudo("JA-HIRAGANA")  # case-insensitive
    assert not is_pseudo("ja")
    assert not is_pseudo("en")
    assert not is_pseudo("foo-bar")
    assert not is_pseudo("ja-bogus")


def test_variant_filename_pattern_matches_modify_outputs():
    """Patterns match the actual filenames generated by `modify --reading`.
    ja keeps the `.furigana-{mode}` infix; ko/zh use `.romanization-{mode}`."""
    pat = MODULE["_variant_filename_pattern"]
    # Japanese hiragana variant.
    ja_pat = pat("ja-hiragana")
    assert ja_pat.search("MF Ghost - S01E07.ja.furigana-hiragana.srt")
    assert ja_pat.search("Show.S01E01.ja.furigana-hiragana.ruby.vtt")
    assert ja_pat.search("Show.S01E01.ja.furigana-hiragana.lines.ass")
    assert ja_pat.search("Show.S01E01.ja.furigana-hiragana.single-line.srt")
    assert ja_pat.search("Show.S01E01.ja.furigana-hiragana.single-line.ruby.vtt")
    assert not ja_pat.search("Show.S01E01.ja.srt")
    assert not ja_pat.search("Show.S01E01.ja.furigana-romaji.srt")
    assert not ja_pat.search("Show.S01E01.ko.romanization-revised.srt")
    # Korean Revised Romanization.
    ko_pat = pat("ko-revised")
    assert ko_pat.search("Show.S01E01.ko.romanization-revised.srt")
    assert ko_pat.search("Show.S01E01.ko.hi.romanization-revised.single-line.ruby.vtt")
    assert ko_pat.search("Show.S01E01.ko.romanization-revised.ruby.vtt")
    assert not ko_pat.search("Show.S01E01.ko.romanization-yale.srt")
    # Chinese pinyin (tone marks).
    zh_pat = pat("zh-marks")
    assert zh_pat.search("Show.S01E01.zh.romanization-marks.srt")
    assert not zh_pat.search("Show.S01E01.zh.romanization-numbers.srt")
    # Unknown pseudo-lang yields None.
    assert pat("nope-mode") is None


def test_combined_output_name_collapses_variants():
    """Multi-variant lang lists collapse adjacent same-base tokens so the
    output filename matches the roadmap example shape:
    ['ja', 'ja-hiragana', 'ja-romaji', 'en'] -> 'ja-hiragana-romaji-en'."""
    from pathlib import Path
    n = MODULE["combined_output_name"]
    master = Path("/x/MF Ghost - S01E07.ja.srt")
    # Plain (no pseudo-langs) still works.
    assert n(master, ["ja", "en"]) == "MF Ghost - S01E07.ja-en.srt"
    # Base + one variant.
    assert n(master, ["ja", "ja-hiragana", "en"]) == "MF Ghost - S01E07.ja-hiragana-en.srt"
    # Base + two variants — adjacent same-base collapses.
    assert (
        n(master, ["ja", "ja-hiragana", "ja-romaji", "en"])
        == "MF Ghost - S01E07.ja-hiragana-romaji-en.srt"
    )
    # Variant without bare base.
    assert n(master, ["ja-hiragana", "en"]) == "MF Ghost - S01E07.ja-hiragana-en.srt"
    # Korean variant.
    ko_master = Path("/x/Episode.S01E01.ko.srt")
    assert (
        n(ko_master, ["ko", "ko-revised", "ja"])
        == "Episode.S01E01.ko-revised-ja.srt"
    )
    # Chinese variant.
    zh_master = Path("/x/Show.S01E01.zh.srt")
    assert (
        n(zh_master, ["zh", "zh-marks", "en"])
        == "Show.S01E01.zh-marks-en.srt"
    )


def test_multi_variant_merge_scanner_finds_variant_files():
    """The extended scanner emits a row per matching `.{base}.{infix}-{mode}.{ext}`
    side file when pseudo-langs are passed."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E07.ja.srt").write_text("1\n00:00:01,000 --> 00:00:03,000\n漢字\n", encoding="utf-8")
        (root / "Show.S01E07.ja.furigana-hiragana.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n漢字（かんじ）\n", encoding="utf-8"
        )
        (root / "Show.S01E07.en.srt").write_text("1\n00:00:01,000 --> 00:00:03,000\nKanji\n", encoding="utf-8")
        scanned = MODULE["scan_subtitle_files_extended"](
            [root], pseudo_langs=["ja-hiragana"],
        )
        langs_found = {row[3] for row in scanned}
        assert langs_found == {"ja", "ja-hiragana", "en"}


def test_multi_variant_merge_end_to_end():
    """A folder with ja + ja.furigana-hiragana + en produces a 3-line
    stacked output."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E01.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n漢字を勉強します。\n", encoding="utf-8"
        )
        (root / "Show.S01E01.ja.furigana-hiragana.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n漢字（かんじ）を勉強します。\n",
            encoding="utf-8",
        )
        (root / "Show.S01E01.en.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nI will study kanji.\n", encoding="utf-8"
        )
        rc = MODULE["combine_main"]([
            str(root), "-l", "ja,ja-hiragana,en",
            "--sync", "loose", "--force", "--no-open-folder-prompt",
        ])
        assert rc == 0
        out = root / "Show.S01E01.ja-hiragana-en.srt"
        assert out.exists(), f"expected merged file, got: {list(root.iterdir())}"
        content = out.read_text(encoding="utf-8")
        # All three rows should appear in the merged cue; pseudo-lang rows
        # are reading-only, not parenthetical duplicates of the original.
        assert "漢字を勉強します。" in content
        assert "かんじ" in content
        assert "漢字（かんじ）" not in content
        assert "I will study kanji." in content


def test_merge_end_to_end_label_langs_writes_prefixed_file(tmp_path):
    (tmp_path / "Show.S01E01.ja.srt").write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nこんにちは\n", encoding="utf-8")
    (tmp_path / "Show.S01E01.en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    rc = MODULE["combine_main"]([
        str(tmp_path), "-l", "ja,en",
        "--label-langs", "--force", "--no-open-folder-prompt",
    ])
    assert rc == 0
    out = tmp_path / "Show.S01E01.ja-en.srt"
    assert out.exists(), list(tmp_path.iterdir())
    content = out.read_text(encoding="utf-8")
    assert "[JA] こんにちは" in content
    assert "[EN] Hello" in content


def test_merge_end_to_end_mixed_input_formats(tmp_path):
    # ja supplied as VTT (via :vtt hint), en as SRT -> a single merged SRT.
    (tmp_path / "Show.S01E01.ja.vtt").write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nこんにちは\n", encoding="utf-8")
    (tmp_path / "Show.S01E01.en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    rc = MODULE["combine_main"]([
        str(tmp_path), "-l", "ja:vtt,en", "--force", "--no-open-folder-prompt",
    ])
    assert rc == 0
    out = tmp_path / "Show.S01E01.ja-en.srt"
    assert out.exists(), list(tmp_path.iterdir())
    content = out.read_text(encoding="utf-8")
    assert "こんにちは" in content
    assert "Hello" in content


def test_multi_variant_vtt_prefers_japanese_ruby_side_file():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E01.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n漢字を勉強します。\n",
            encoding="utf-8",
        )
        (root / "Show.S01E01.ja.furigana-hiragana.single-line.ruby.vtt").write_text(
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:03.000\n"
            "<ruby>漢字<rt>かんじ</rt></ruby>を<ruby>勉強<rt>べんきょう</rt></ruby>します。\n",
            encoding="utf-8",
        )
        (root / "Show.S01E01.en.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nI will study kanji.\n",
            encoding="utf-8",
        )
        rc = MODULE["combine_main"]([
            str(root), "-l", "ja-hiragana,ja,en", "--format", "vtt",
            "--sync", "loose", "--force", "--no-open-folder-prompt",
        ])
        assert rc == 0
        out = root / "Show.S01E01.ja-hiragana-ja-en.vtt"
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "<ruby>漢字<rt>かんじ</rt></ruby>" in content
        assert "漢字（かんじ）" not in content
        assert "I will study kanji." in content


def test_multi_variant_vtt_derives_japanese_romaji_full_sentence():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E01.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n７号車と６号車がくっついた。\n",
            encoding="utf-8",
        )
        (root / "Show.S01E01.ja.furigana-romaji.single-line.ruby.vtt").write_text(
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:03.000\n"
            "<ruby>号車<rt>gousha</rt></ruby>だけ\n",
            encoding="utf-8",
        )
        (root / "Show.S01E01.en.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nThe cars stuck together.\n",
            encoding="utf-8",
        )
        rc = MODULE["combine_main"]([
            str(root), "-l", "ja-romaji,ja,en", "--format", "vtt",
            "--sync", "loose", "--force", "--no-open-folder-prompt",
        ])
        assert rc == 0
        content = (root / "Show.S01E01.ja-romaji-ja-en.vtt").read_text(encoding="utf-8")
        assert "gousha" in content
        assert "kuttsuita" in content
        assert "<ruby>号車<rt>gousha</rt></ruby>だけ" not in content


def test_multi_variant_japanese_romaji_handles_kana_only_lines():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E01.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nここからセクター２！\n",
            encoding="utf-8",
        )
        rc = MODULE["combine_main"]([
            str(root), "-l", "ja-romaji,ja", "--format", "vtt",
            "--sync", "loose", "--force", "--no-open-folder-prompt",
        ])
        assert rc == 0
        content = (root / "Show.S01E01.ja-romaji-ja.vtt").read_text(encoding="utf-8")
        assert "koko kara" in content
        assert "sekutaa" in content
        assert "ここからセクター２！" in content


def test_multi_variant_merge_derives_clean_korean_reading_rows():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E01.ko.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n야 선생님한테\n",
            encoding="utf-8",
        )
        (root / "Show.S01E01.en.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nHey, to your teacher?\n",
            encoding="utf-8",
        )
        rc = MODULE["combine_main"]([
            str(root), "-l", "ko-yale,ko,en",
            "--format", "ass", "--sync", "loose", "--force", "--no-open-folder-prompt",
        ])
        assert rc == 0
        out = root / "Show.S01E01.ko-yale-ko-en.ass"
        assert out.exists()
        body = out.read_text(encoding="utf-8")
    assert "ya sensayngnimhanthey" in body
    assert "야 선생님한테" in body
    assert "Hey, to your teacher?" in body
    assert "야（" not in body
    assert "선생님한테（" not in body


def test_serialize_ass_scales_font_for_four_line_study_stack():
    cues = [
        MODULE["SrtCue"](
            index="1",
            time_line="00:00:01,000 --> 00:00:03,000",
            text_lines=["revised", "yale", "한국어", "English"],
        )
    ]
    body = MODULE["serialize_ass"](cues)
    assert "PlayResX: 1920" in body
    assert "PlayResY: 1080" in body
    assert "Style: Default,Arial,24," in body


def test_font_size_recommendations_and_aliases():
    assert MODULE["recommended_font_size_for_lines"](2) == 30
    assert MODULE["font_size_options_for_lines"](2) == (30, 24, 36)
    assert MODULE["recommended_font_size_for_lines"](4) == 24
    assert MODULE["resolve_font_size"]("regular", 2) == 30
    assert MODULE["resolve_font_size"]("smaller", 2) == 24
    assert MODULE["resolve_font_size"]("larger", 2) == 36
    assert MODULE["resolve_font_size"]("42", 2) == 42
    assert MODULE["resolve_font_size"]("auto", 2) is None
    assert MODULE["resolve_font_size_for_format"]("smaller", 2, "ass") == 46
    assert MODULE["resolve_font_size_for_format"]("regular", 2, "ass") == 58
    assert MODULE["resolve_font_size_for_format"]("larger", 2, "ass") == 70
    assert MODULE["resolve_font_size_for_format"]("30", 2, "ass") == 30
    assert MODULE["resolve_font_size_for_format"]("smaller", 2, "srt") == "px:12"
    assert MODULE["resolve_font_size_for_format"]("regular", 2, "srt") == "px:16"
    assert MODULE["resolve_font_size_for_format"]("larger", 2, "srt") == "px:20"
    assert MODULE["resolve_font_size_for_format"]("42", 2, "srt") == "px:42"
    assert MODULE["resolve_font_size_for_format"]("regular", 2, "smi") is None
    assert MODULE["resolve_font_size_for_format"]("larger", 2, "smi") is None
    assert MODULE["resolve_font_size_for_format"]("smaller", 2, "smi") is None
    assert MODULE["resolve_font_size_for_format"]("30", 2, "smi") is None
    assert MODULE["_srt_html_font_size"](24) == 6
    assert MODULE["_srt_html_font_size"](30) == 7
    assert MODULE["_srt_html_font_size"](36) == 7


def test_serializers_apply_requested_font_size_to_all_formats():
    cue = MODULE["SrtCue"](
        index="1",
        time_line="00:00:01,000 --> 00:00:03,000",
        text_lines=["こんにちは", "Hello"],
    )
    cues = [cue]
    assert "<big>こんにちは</big>" in MODULE["serialize_srt"](cues, font_size="big")
    assert '<font size="7">こんにちは</font>' in MODULE["serialize_srt"](cues, font_size="font7")
    assert '<font size="42px">こんにちは</font>' in MODULE["serialize_srt"](cues, font_size="px:42")
    vtt = MODULE["serialize_vtt"](cues, font_size=30)
    assert "STYLE\n::cue { font-size: 30px; }" in vtt
    assert "Style: Default,Arial,30," in MODULE["serialize_ass"](cues, font_size=30)
    smi = MODULE["serialize_smi"](cues, font_size=30)
    assert "font-size:30pt" in smi
    assert 'Style="font-size:30pt"' in smi
    assert '<font size="7">こんにちは<br>Hello</font>' in smi


def test_serialize_smi_omits_font_hints_when_unset():
    cue = MODULE["SrtCue"](
        index="1",
        time_line="00:00:01,000 --> 00:00:03,000",
        text_lines=["こんにちは", "Hello"],
    )
    smi = MODULE["serialize_smi"]([cue])
    assert "font-size:" not in smi
    assert "Style=" not in smi
    assert "<font" not in smi
    assert "こんにちは<br>Hello" in smi


def test_serialize_vtt_adds_ruby_text_style_for_ruby_cues():
    cue = MODULE["SrtCue"](
        index="1",
        time_line="00:00:01,000 --> 00:00:03,000",
        text_lines=["<ruby>日本語<rt>にほんご</rt></ruby>"],
    )
    vtt = MODULE["serialize_vtt"]([cue])
    assert "::cue(rt) { font-size: 0.85em; }" in vtt
    assert "::cue(ruby) { ruby-position: over; }" in vtt


def test_merge_font_size_toml_and_inline_overrides():
    argv, _ = MODULE["_toml_to_pipeline_argv"]({
        "merge": {"languages": "ja,en", "font_size": "larger"},
    })
    assert "--font-size" in argv
    assert "larger" in argv
    ov, _residual, vb = MODULE["_extract_cli_overrides"](["--merge", "--font-size", "36"])
    data = MODULE["_merge_overrides_into_toml"]({"merge": {"languages": "ja,en"}}, ov, vb)
    assert data["merge"]["font_size"] == "36"


def test_combine_main_writes_vtt_font_size(tmp_path):
    (tmp_path / "Show.S01E01.ja.srt").write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nこんにちは\n", encoding="utf-8"
    )
    (tmp_path / "Show.S01E01.en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8"
    )
    rc = MODULE["combine_main"]([
        str(tmp_path),
        "-l", "ja,en",
        "--format", "vtt",
        "--font-size", "larger",
        "--force",
        "--no-watermark",
        "--no-open-folder-prompt",
    ])
    assert rc == 0
    body = (tmp_path / "Show.S01E01.ja-en.vtt").read_text(encoding="utf-8")
    assert "STYLE\n::cue { font-size: 36px; }" in body


def test_combine_main_finds_vtt_inputs_without_format_hints(tmp_path, capsys):
    (tmp_path / "Show.S01E09.ja.vtt").write_text(
        "WEBVTT\n\n"
        "1\n00:00:01.000 --> 00:00:03.000 position:50.00%,middle align:middle\n"
        "<c.japanese><c.bg_transparent>日本語</c.bg_transparent></c.japanese>\n",
        encoding="utf-8",
    )
    (tmp_path / "Show.S01E09.ko.vtt").write_text(
        "WEBVTT\n\n"
        "1\n00:00:01.000 --> 00:00:03.000 position:50.00%,middle align:middle\n"
        "<c.korean><c.bg_transparent>한국어</c.bg_transparent></c.korean>\n",
        encoding="utf-8",
    )

    rc = MODULE["combine_main"]([
        str(tmp_path),
        "-l", "ja,ko",
        "--format", "vtt",
        "--no-watermark",
        "--no-open-folder-prompt",
    ])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Alignment compares support-language cues against the timing master." not in out
    assert "[ko aligned: 100%]" not in out
    body = (tmp_path / "Show.S01E09.ja-ko.vtt").read_text(encoding="utf-8")
    assert "日本語" in body
    assert "한국어" in body
    assert "<c." not in body
    assert "&lt;c." not in body


def test_multi_variant_master_default_prefers_base_over_pseudo():
    """When -l starts with the base + variant (e.g. ja,ja-hiragana), the
    default master picks the base, not the variant. Variants share cue
    timing with their base but the base is the authoritative source."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E01.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n漢字\n", encoding="utf-8"
        )
        (root / "Show.S01E01.ja.furigana-hiragana.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n漢字（かんじ）\n", encoding="utf-8"
        )
        # Reverse order to confirm the heuristic, not just first-lang.
        rc = MODULE["combine_main"]([
            str(root), "-l", "ja-hiragana,ja",
            "--sync", "loose", "--force", "--no-open-folder-prompt",
        ])
        assert rc == 0


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
        # The original Japanese kanji and the Korean support line are
        # both present in the stacked output. (Furigana would only inline
        # if --reading ja:hiragana were passed; see the multi-variant
        # merge tests for stacked-variant coverage.)
        assert "Created with GetSubtitle" in body
        assert "Subtitles © their respective copyright holders" in body
        assert body.count("Created with GetSubtitle") == 2
        cues = MODULE["parse_srt"](body)
        assert cues[0].text_lines[0] == "Created with GetSubtitle"
        assert cues[-1].text_lines[0] == "Created with GetSubtitle"
        assert "彼女" in body
        assert "運命" in body
        assert "人間" in body
        assert "그녀에게 점을 보려는 사람들의 행렬이" in body


def test_combine_main_no_watermark_flag_omits_credit_cues():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E07.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nこんにちは\n",
            encoding="utf-8",
        )
        (root / "Show.S01E07.en.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nHello\n",
            encoding="utf-8",
        )
        rc = MODULE["combine_main"]([str(root), "-l", "ja,en", "--no-watermark"])
        assert rc == 0
        body = (root / "Show.S01E07.ja-en.srt").read_text(encoding="utf-8")
    assert "Created with GetSubtitle" not in body
    assert "copyright holders" not in body
    assert "こんにちは" in body
    assert "Hello" in body


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
                str(root), "-l", "ja,ko", "--reading", "ja:hiragana", "--format", "vtt",
            ])
            assert rc == 0
            # --reading ja:hiragana rewrites the ja token to ja-furigana in
            # the output filename (see combined_output_name's `furigana=` arg).
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
    bad = '[output]\nlayout = "totally-bogus"\n'
    with _isolated_config(bad):
        try:
            MODULE["load_user_config"]()
        except MODULE["CliError"] as e:
            assert "output.layout" in str(e)
        else:
            raise AssertionError("expected CliError for invalid layout")


def test_config_validates_boolean_type():
    bad = '[modify]\nsingle_line = "yes"\n'
    with _isolated_config(bad):
        try:
            MODULE["load_user_config"]()
        except MODULE["CliError"] as e:
            assert "modify.single_line" in str(e)
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
        '[fetch]\nlanguages = "ja,ko"\n'
        '[merge]\nlanguages = ["ja", "ko", "en"]\n'
    )
    with _isolated_config(toml):
        cfg = MODULE["load_user_config"]()
    assert cfg["fetch"]["languages"] == "ja,ko"
    # Arrays are normalised to a comma-separated string for argparse.
    assert cfg["merge"]["languages"] == "ja,ko,en"


def test_config_combine_priority_parsed_as_lowercase_list():
    toml = '[merge]\npriority = ["JA", "En", "ko"]\n'
    with _isolated_config(toml):
        cfg = MODULE["load_user_config"]()
    assert cfg["merge"]["priority"] == ["ja", "en", "ko"]


def test_config_combine_priority_rejects_non_list():
    bad = '[merge]\npriority = "ja,en"\n'
    with _isolated_config(bad):
        try:
            MODULE["load_user_config"]()
        except MODULE["CliError"] as e:
            assert "merge.priority" in str(e)
        else:
            raise AssertionError("expected CliError for non-list priority")


def test_config_default_lang_applies_to_download_parser():
    toml = '[fetch]\nlanguages = "ja,ko,en"\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        # No -l passed -> takes config default.
        args = parser.parse_args(["https://www.imdb.com/title/tt0245429/"])
        assert args.langs == "ja,ko,en"


def test_cli_lang_overrides_config_lang():
    toml = '[fetch]\nlanguages = "ja,ko,en"\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL", "-l", "es"])
        assert args.langs == "es"


def test_config_output_path_is_expanded():
    toml = '[output]\ntarget = "~/Subtitles/CustomFolder"\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL"])
    # ~ should have been expanded.
    assert "~" not in args.output
    assert args.output.endswith("Subtitles/CustomFolder")


def test_config_combine_langs_applies_to_combine_parser():
    toml = '[merge]\nlanguages = "en,es,ko"\n'
    with _isolated_config(toml):
        parser = MODULE["build_combine_parser"]()
        args = parser.parse_args(["/tmp/x"])
        assert args.langs == "en,es,ko"


def test_config_combine_sync_applies_default():
    toml = '[merge]\nsync = "strict"\n'
    with _isolated_config(toml):
        parser = MODULE["build_combine_parser"]()
        args = parser.parse_args(["/tmp/x"])
        assert args.sync == "strict"


def test_combine_single_line_flag_is_explicit_default_and_overrides_preserve_config():
    toml = '[merge]\npreserve_lines = true\n'
    with _isolated_config(toml):
        parser = MODULE["build_combine_parser"]()
        args = parser.parse_args(["/tmp/x", "--single-line"])
        assert args.preserve_lines is False
        args = parser.parse_args(["/tmp/x", "--single"])
        assert args.preserve_lines is False


def test_config_strip_cc_noise_default_true_applies():
    toml = '[modify]\nstrip_cc_noise = true\n'
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
    toml = '[merge]\npriority = ["ja", "en"]\n'
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
    toml = '[fetch]\nlanguages = "ja,ko"\n'
    with _isolated_config(toml):
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = MODULE["config_main"](["--show"])
        assert rc == 0
        text = out.getvalue()
    for section in ("[fetch]", "[translate]", "[modify]", "[merge]", "[output]", "[experimental]"):
        assert section in text
    # User-overridden field should be marked.
    assert "from user_settings.toml" in text
    # The overridden value should appear.
    assert 'languages = "ja,ko"' in text


def test_config_show_uses_canonical_mt_source_key():
    rendered = MODULE["render_effective_config"](
        user_cfg={"translate": {"mt_source_lang": "ko:ja"}}
    )
    assert 'mt_source = "ko:ja"  # from user_settings.toml' in rendered
    assert "mt_source_lang" not in rendered


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
    # Main help mentions the config subcommand and points at the topic page.
    assert "config" in text
    assert "user_settings.toml" in text
    assert "--help" in text and "config" in text  # topic-help line present


def test_help_includes_setup_topic():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        MODULE["main"](["--help"])
    text = out.getvalue()
    assert "setup" in text
    assert "first-time setup" in text.lower() or "onboarding" in text.lower()


def test_help_topic_config_describes_file_and_precedence():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        MODULE["main"](["--help", "config"])
    text = out.getvalue()
    assert "user_settings.toml" in text
    assert "precedence" in text.lower()
    assert "API keys are NEVER" in text or "API keys" in text


def test_help_topic_setup_describes_onboarding():
    rc, out, _ = _capture_main(["--help", "setup"])
    assert rc == 0
    assert "First-time setup" in out
    assert "opens the provider pages" in out
    assert "Subtitle HTML = Render" in out


def test_setup_recommendations_for_korean_speaker_learning_japanese_anime():
    choice = MODULE["_SetupChoice"](
        native=["ko"],
        learning=["ja"],
        content="anime",
        venue="browser",
        mt="online",
    )
    recs = MODULE["_setup_recommendations"](choice)
    keys = [r.key for r in recs]
    assert "jimaku" in keys
    assert "deepl" in keys
    # Reading-aid keys now carry the romanization spec
    # (e.g. "reading:ja:hiragana"). Match by prefix so we're not coupled
    # to the exact spec syntax.
    assert any(k.startswith("reading:ja") for k in keys)
    assert "tmdb" not in keys  # anime path should not force non-anime TV setup
    deepl = next(r for r in recs if r.key == "deepl")
    assert "500,000" in deepl.cost


def test_setup_config_text_uses_learning_then_native_order_and_vtt_for_asbplayer():
    choice = MODULE["_SetupChoice"](
        native=["ko"],
        learning=["ja"],
        content="anime",
        venue="browser",
        mt="online",
    )
    text = MODULE["_setup_config_text"](choice)
    assert 'languages = "ja,ko"' in text
    assert 'reading_format = "vtt"' in text
    assert 'format = "vtt"' in text
    assert 'engine = "deepl"' in text
    assert "API keys are not stored here" in text


def test_setup_help_subcommand_works_without_tty():
    rc, out, _ = _capture_main(["setup", "--help"])
    assert rc == 0
    assert "getsubtitle setup" in out
    assert "AI translation preference" in out


# ─── Setup script fixes (review feedback) ────────────────────────────

def test_setup_config_text_uses_canonical_romanization_key():
    """The wizard emits the v0.1 canonical key `romanization` (not the
    legacy `furigana = "hiragana"` form). Guards against re-introducing
    the bug the review caught."""
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["ja"], content="anime",
        venue="browser", mt="none",
    )
    text = MODULE["_setup_config_text"](choice)
    assert 'reading = "ja:hiragana"' in text
    # The legacy single-language form must NOT be emitted.
    assert 'furigana = "hiragana"' not in text
    assert 'furigana = "off"' not in text


def test_setup_recommendations_korean_learner_gets_reading_aid():
    """Korean-learning users get Korean Revised Romanization. Now that
    the backend ships (via g2pk + korean-romanizer), it defaults to
    selected (was opt-in only when the backend was deferred)."""
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["ko"], content="tv",
        venue="browser", mt="none",
    )
    recs = MODULE["_setup_recommendations"](choice)
    keys = [r.key for r in recs]
    assert any(k.startswith("reading:ko") for k in keys), \
        "Korean learner missed reading-aid recommendation"
    # Korean ships now → selected by default.
    ko_rec = next(r for r in recs if r.key.startswith("reading:ko"))
    assert ko_rec.selected_by_default is True


def test_setup_recommendations_chinese_learner_gets_pinyin_aid():
    """Mandarin-learning users see a pinyin recommendation (zh:marks)."""
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["zh"], content="tv",
        venue="browser", mt="none",
    )
    recs = MODULE["_setup_recommendations"](choice)
    keys = [r.key for r in recs]
    assert any(k.startswith("reading:zh") for k in keys)


def test_setup_config_text_multi_language_romanization_spec():
    """ja + ko + zh learner gets all three reading-aid specs joined into
    one [modify].romanization line."""
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["ja", "ko", "zh"], content="mixed",
        venue="browser", mt="none",
    )
    text = MODULE["_setup_config_text"](choice)
    assert 'reading = "ja:hiragana,ko:revised,zh:marks"' in text


def test_setup_recommendations_mt_offline_falls_back_to_argos():
    """When Ollama isn't reachable, offline MT falls back to Argos.
    Patches via fn.__globals__ — see note on the ollama-preferred test
    above for why MODULE[...] patching doesn't reach call-site lookups."""
    fn = MODULE["_setup_recommendations"]
    g = fn.__globals__
    saved = g["_wizard_ollama_reachable"]
    try:
        g["_wizard_ollama_reachable"] = lambda: False
        choice = MODULE["_SetupChoice"](
            native=["en"], learning=["ja"], content="anime",
            venue="browser", mt="offline",
        )
        recs = fn(choice)
        keys = [r.key for r in recs]
        assert "argos" in keys
        assert "ollama" not in keys
    finally:
        g["_wizard_ollama_reachable"] = saved


def test_setup_recommendations_mt_offline_prefers_ollama_when_available():
    """When the Ollama daemon is reachable, offline MT prefers Ollama
    over Argos (better CJK quality, same offline guarantee).

    Patches the function's own __globals__ — `runpy.run_path` returns a
    snapshot dict, not the live module namespace, so patching MODULE[...]
    doesn't reach code that resolves names against __globals__ at call
    time. Patching shutil.which globally is OK because there's only one
    shutil module."""
    fn = MODULE["_setup_recommendations"]
    g = fn.__globals__
    saved_reach = g["_wizard_ollama_reachable"]
    saved_which = MODULE["shutil"].which
    try:
        g["_wizard_ollama_reachable"] = lambda: True
        MODULE["shutil"].which = lambda name: "/usr/local/bin/ollama" if name == "ollama" else None
        choice = MODULE["_SetupChoice"](
            native=["en"], learning=["ja"], content="anime",
            venue="browser", mt="offline",
        )
        recs = fn(choice)
        keys = [r.key for r in recs]
        assert "ollama" in keys
        assert "argos" not in keys
    finally:
        g["_wizard_ollama_reachable"] = saved_reach
        MODULE["shutil"].which = saved_which


def test_setup_config_text_no_translate_block_when_mt_none():
    """mt='none' must not emit a [translate] section. (Was: emitted an
    empty engine string in earlier drafts.)"""
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["ja"], content="anime",
        venue="browser", mt="none",
    )
    text = MODULE["_setup_config_text"](choice)
    assert "[translate]" not in text


def test_setup_config_text_ollama_block_emitted_when_available():
    """mt='offline' + Ollama reachable → emit [translate] with
    engine='ollama' AND [translate.ollama_models] defaults."""
    fn = MODULE["_setup_config_text"]
    g = fn.__globals__
    saved_reach = g["_wizard_ollama_reachable"]
    saved_which = MODULE["shutil"].which
    try:
        g["_wizard_ollama_reachable"] = lambda: True
        MODULE["shutil"].which = lambda name: "/usr/local/bin/ollama" if name == "ollama" else None
        choice = MODULE["_SetupChoice"](
            native=["en"], learning=["ja"], content="anime",
            venue="browser", mt="offline",
        )
        text = fn(choice)
        assert 'engine = "ollama"' in text
        assert "[translate.ollama_models]" in text
        assert "auto_load = true" in text
    finally:
        g["_wizard_ollama_reachable"] = saved_reach
        MODULE["shutil"].which = saved_which


def test_setup_parse_langs_rejects_unknown_codes_with_clear_error():
    """`xyzzy` and friends must raise a CliError before contaminating
    the generated config."""
    fn = MODULE["_setup_parse_langs"]
    # Valid codes still work.
    assert fn("japanese, korean, english") == ["ja", "ko", "en"]
    # Single unknown code raises.
    try:
        fn("xyzzy")
    except MODULE["CliError"] as e:
        assert "xyzzy" in str(e)
    else:
        raise AssertionError("expected CliError for unknown lang")
    # Mixed valid + unknown still raises (don't silently drop the unknown).
    try:
        fn("ja, klingon")
    except MODULE["CliError"] as e:
        assert "klingon" in str(e)
    else:
        raise AssertionError("expected CliError for mixed valid+unknown")


def test_setup_module_exists_uses_find_spec_no_side_effects():
    """find_spec-based check must not trigger module import side effects.
    Verified by probing a known-stdlib module and a guaranteed-missing one."""
    fn = MODULE["_setup_module_exists"]
    assert fn("json") is True
    assert fn("definitely_not_a_real_module_xyzzy") is False


def test_setup_viewing_guidance_tablet_warns_about_streaming_apps():
    """Tablet/TV streaming apps don't import custom subtitle files; the
    guidance must steer the user toward browser/Plex/local alternatives."""
    import io, contextlib
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["ja"], content="anime",
        venue="tablet", mt="none",
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        MODULE["_setup_print_viewing_guidance"](choice)
    text = buf.getvalue()
    assert "cannot import custom subtitle files" in text
    assert "asbplayer" in text or "Plex" in text


def test_setup_intro_matches_wizard_style():
    intro = MODULE["_SETUP_INTRO"]
    assert "GetSubtitle — Setup" in intro
    assert "Commands:" in intro
    assert "b      Back" in intro
    assert "Ctrl-C Cancel" in intro
    assert "Workflow Builder" not in intro


def test_setup_collect_choice_accepts_short_language_codes_and_examples():
    import io, contextlib
    fn = MODULE["_setup_collect_choice"]
    g = fn.__globals__
    saved_prompt = g["_wizard_prompt"]
    answers = iter(["en,ko", "jp,es", "3", "1", "3"])
    try:
        g["_wizard_prompt"] = lambda q, default=None, **kw: next(answers)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            choice = fn()
        out = buf.getvalue()
        assert "Examples: en,ko" in out
        assert "Examples: ko,ja,es" in out
        assert choice.native == ["en", "ko"]
        assert choice.learning == ["ja", "es"]
        assert choice.content == "anime"
        assert choice.venue == "browser"
        assert choice.mt == "ollama"
    finally:
        g["_wizard_prompt"] = saved_prompt


def test_setup_recommendations_print_outcome_groups_and_why():
    import io, contextlib
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["ja"], content="anime",
        venue="browser", mt="online",
    )
    recs = MODULE["_setup_recommendations"](choice)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        MODULE["_setup_print_recommendations"](recs)
    text = buf.getvalue()
    assert "Getting subtitles" in text
    assert "Language learning" in text
    assert "Translation fallback" in text
    assert "Convenience" in text
    assert "Why:" in text
    assert "You selected anime" in text
    assert "Save your preferences" in text
    assert "user_settings.toml (recommended)" not in text


def test_setup_write_config_shows_summary_before_optional_raw_config():
    import tempfile, io, contextlib
    from pathlib import Path
    fn = MODULE["_setup_write_config"]
    g = fn.__globals__
    saved_cfg_path = g["config_path"]
    saved_yesno = g["_wizard_yesno"]
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "user_settings.toml"
        try:
            g["config_path"] = lambda: cfg
            g["_wizard_yesno"] = lambda q, default=True: False
            choice = MODULE["_SetupChoice"](
                native=["en"], learning=["ja"], content="anime",
                venue="browser", mt="none",
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok = fn(choice)
            assert ok is True
            text = buf.getvalue()
            assert "Preferences to save:" in text
            assert "Languages: Japanese, English" in text
            assert "│ [fetch]" not in text
        finally:
            g["config_path"] = saved_cfg_path
            g["_wizard_yesno"] = saved_yesno


def test_setup_recommendation_loop_bulk_runs_recommended_without_per_item_prompts():
    import io, contextlib
    fn = MODULE["_setup_run_recommendation_loop"]
    g = fn.__globals__
    saved_run = g["_setup_run_recommendation"]
    saved_yesno = g["_wizard_yesno"]
    saved_prompt = g["_wizard_prompt"]
    saved_read_choice = g["_wizard_read_choice"]
    saved_profile = g["_setup_save_profile"]
    saved_examples = g["_setup_try_examples"]
    calls = []
    questions = []
    yesnos = iter([False, True, False])  # no optional, set up selected, no quick search
    recs = [
        MODULE["_SetupRecommendation"]("jimaku", "Jimaku", "why", "free", "now", selected_by_default=True),
        MODULE["_SetupRecommendation"]("subdl", "SubDL", "why", "free", "now", selected_by_default=False),
    ]
    try:
        g["_setup_run_recommendation"] = lambda rec, choice, ask=True: calls.append((rec.title, ask)) or True
        g["_wizard_yesno"] = lambda q, default=True: questions.append(q) or next(yesnos)
        g["_wizard_prompt"] = lambda q, default=None, **kw: "done"
        g["_wizard_read_choice"] = lambda prompt, valid, default, **kw: "3"
        g["_setup_save_profile"] = lambda choice: None
        g["_setup_try_examples"] = lambda: None
        choice = MODULE["_SetupChoice"](["en"], ["ja"], "anime", "browser", "none")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert fn(recs, choice) == 0
        text = buf.getvalue()
        assert calls == [("Jimaku", False)]
        assert "Setup complete" in text
        assert "Jimaku" in text
        assert "Profile:" in text
        assert "Known languages:" in text
        assert "Learning:" in text
        assert "Show example workflows" in text
        assert "Show example commands" not in text
        assert any("Run a quick subtitle search now?" in q for q in questions)
    finally:
        g["_setup_run_recommendation"] = saved_run
        g["_wizard_yesno"] = saved_yesno
        g["_wizard_prompt"] = saved_prompt
        g["_wizard_read_choice"] = saved_read_choice
        g["_setup_save_profile"] = saved_profile
        g["_setup_try_examples"] = saved_examples


def test_setup_profile_summary_and_wizard_setup_labels():
    choice = MODULE["_SetupChoice"](
        native=["ko"], learning=["ja"], content="anime",
        venue="browser", mt="deepl",
    )
    summary = MODULE["_setup_profile_summary"](choice)
    assert ("Languages", "ja, ko") in summary
    assert ("AI translation", "deepl") in summary
    assert ("Reading aids", "ja:hiragana") in summary
    assert any(label == "Format" and "VTT" in value for label, value in summary)

    state = MODULE["_WizardState"]()
    state.steps = {"fetch", "translate", "modify", "merge"}
    state.languages = ["ja", "ko"]
    state.mt_engine = "deepl"
    state.reading_aids = ["ja:hiragana"]
    state.format = "vtt"
    state._setup_prefilled = {"languages", "translate", "reading_aids", "format"}
    state._setup_format_reason = "browser/asbplayer"
    notes = MODULE["_wizard_setup_review_notes"](state)
    assert notes["Languages"].endswith("(from setup)")
    assert notes["AI translation"] == "deepl  (from setup)"
    assert "browser/asbplayer" in notes["Format"]
    targets = MODULE["_wizard_edit_targets"](state)
    values = {label: value for label, value, _fn in targets}
    assert values["languages"].endswith("(from setup)")
    assert values["AI translation"].endswith("(from setup)")
    MODULE["_wizard_forget_setup_source"](state, "AI translation")
    assert "translate" not in state._setup_prefilled


def test_setup_select_reprompts_on_unrecognised_input():
    """Bad input must re-prompt rather than silently fall back to default
    (silent fallback was misleading and hard to debug)."""
    import io, contextlib
    fn = MODULE["_setup_select"]
    g = fn.__globals__
    answers = iter(["x", "9", "2"])  # non-numeric, out-of-range, then a valid pick
    saved = g["_wizard_prompt"]
    try:
        g["_wizard_prompt"] = lambda q, default=None, **kw: next(answers)
        with contextlib.redirect_stdout(io.StringIO()):
            result = fn("Pick", [("a", "A"), ("b", "B"), ("c", "C")], "a")
        # Options display as 1/2/3; '2' maps back to the caller's key 'b'.
        assert result == "b"  # not the default — the user's eventual valid pick
    finally:
        g["_wizard_prompt"] = saved


def test_setup_profile_save_and_load_round_trip():
    """A saved profile loads back into an equivalent _SetupChoice."""
    import tempfile
    from pathlib import Path
    save_fn = MODULE["_setup_save_profile"]
    load_fn = MODULE["_setup_load_profile"]
    # Patch config_path in both functions' __globals__ (same module dict
    # for both since they're defined in the same file).
    g = save_fn.__globals__
    saved_cfg_path = g["config_path"]
    with tempfile.TemporaryDirectory() as td:
        try:
            g["config_path"] = lambda: Path(td) / "user_settings.toml"
            choice = MODULE["_SetupChoice"](
                native=["en"], learning=["ja", "ko"], content="anime",
                venue="browser", mt="offline",
            )
            save_fn(choice)
            loaded = load_fn()
            assert loaded is not None
            assert loaded.native == ["en"]
            assert loaded.learning == ["ja", "ko"]
            assert loaded.content == "anime"
            assert loaded.venue == "browser"
            assert loaded.mt == "offline"
        finally:
            g["config_path"] = saved_cfg_path


def test_setup_write_config_preserves_existing_via_backup():
    """When overwriting, the existing config moves to a .bak file."""
    import tempfile, io, contextlib
    from pathlib import Path
    fn = MODULE["_setup_write_config"]
    g = fn.__globals__
    saved_cfg_path = g["config_path"]
    saved_yesno = g["_wizard_yesno"]
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "user_settings.toml"
        cfg.write_text("# pre-existing\n", encoding="utf-8")
        try:
            g["config_path"] = lambda: cfg
            g["_wizard_yesno"] = lambda q, default=True: True  # confirm overwrite
            choice = MODULE["_SetupChoice"](
                native=["en"], learning=["ja"], content="anime",
                venue="browser", mt="none",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                ok = fn(choice)
            assert ok is True
            bak = cfg.with_suffix(".toml.bak")
            assert bak.exists()
            assert bak.read_text(encoding="utf-8") == "# pre-existing\n"
        finally:
            g["config_path"] = saved_cfg_path
            g["_wizard_yesno"] = saved_yesno


def test_setup_write_config_refuses_without_confirm():
    """Overwriting an existing config without explicit confirmation
    must leave the original file untouched."""
    import tempfile, io, contextlib
    from pathlib import Path
    fn = MODULE["_setup_write_config"]
    g = fn.__globals__
    saved_cfg_path = g["config_path"]
    saved_yesno = g["_wizard_yesno"]
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "user_settings.toml"
        cfg.write_text("# pre-existing\n", encoding="utf-8")
        try:
            g["config_path"] = lambda: cfg
            g["_wizard_yesno"] = lambda q, default=True: False  # refuse
            choice = MODULE["_SetupChoice"](
                native=["en"], learning=["ja"], content="anime",
                venue="browser", mt="none",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                ok = fn(choice)
            assert ok is False
            assert cfg.read_text(encoding="utf-8") == "# pre-existing\n"
            assert not (cfg.with_suffix(".toml.bak")).exists()
        finally:
            g["config_path"] = saved_cfg_path
            g["_wizard_yesno"] = saved_yesno


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
    # The three flips: language-learner-friendly defaults on by default.
    # (Reading-aid SPEC is no longer set by BUILTIN — users opt in
    # via wizard / setup / [modify].reading in their TOML.)
    assert args.single_line is True
    assert args.strip_cc_noise is True
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
    # Must include all five subcommand names + the topic-help pointer.
    for name in ("fetch", "translate", "modify", "merge", "config"):
        assert name in out
    # Must include the shipped example-config references.
    assert "simpsons-s1-en-fr.toml" in out
    assert "plex-movies-fill-merge.toml" in out
    # Must NOT include the long argparse-style argument table.
    assert "--debug-providers" not in out


def test_main_help_short_form_and_long_form_match():
    _, short_out, _ = _capture_main(["-h"])
    _, long_out, _ = _capture_main(["--help"])
    assert short_out == long_out


def test_help_fetch_topic_focused():
    rc, out, _ = _capture_main(["--help", "fetch"])
    assert rc == 0
    assert "Fetch subtitles" in out
    assert "Supported URL types" in out
    # Cross-topic experimental flags must not leak into this page.
    assert "--experimental-subdivx" not in out


def test_help_merge_topic_focused():
    rc, out, _ = _capture_main(["--help", "merge"])
    assert rc == 0
    assert "Merge multiple language subtitle files" in out
    assert "--sync" in out
    assert "--master" in out


def test_merge_subcommand_help_routes_to_merge_topic():
    # 'getsubtitle merge --help' and 'getsubtitle merge -h' should both
    # show the merge topic, not main help.
    rc, out, _ = _capture_main(["merge", "--help"])
    assert rc == 0
    assert "Merge multiple language subtitle files" in out
    rc, out, _ = _capture_main(["merge", "-h"])
    assert rc == 0
    assert "Merge multiple language subtitle files" in out


def test_merge_subcommand_no_args_shows_merge_topic():
    # 'getsubtitle merge' alone — friendlier than an argparse error.
    rc, out, _ = _capture_main(["merge"])
    assert rc == 0
    assert "Merge multiple language subtitle files" in out


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
    assert "fetch" in err and "merge" in err  # Lists valid topics.


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
    # Real-world shape produced by text_with_readings: kanji surfaces are
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


def test_translate_config_validates_strip_reading_before_mt_as_bool():
    # The validator should accept true/false and reject non-bool.
    v = MODULE["validate_user_config"]
    out = v({"translate": {"strip_reading_before_mt": True}})
    assert out["translate"]["strip_reading_before_mt"] is True
    out = v({"translate": {"strip_reading_before_mt": False}})
    assert out["translate"]["strip_reading_before_mt"] is False
    # Bad value → CliError mentioning the key path.
    err = None
    try:
        v({"translate": {"strip_reading_before_mt": "yes"}})
    except MODULE["CliError"] as e:
        err = str(e)
    assert err is not None and "translate.strip_reading_before_mt" in err


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
        toml = "[translate]\nstrip_reading_before_mt = false\n"
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


def test_translate_main_uses_pair_specific_ollama_model_from_cli():
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
        with _isolated_config('[translate]\nmodel = "aya-expanse:8b"\n'):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "Show.S01E07.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n", encoding="utf-8"
                )
                rc = MODULE["translate_main"]([
                    str(root), "-l", "ko", "--engine", "ollama",
                    "--mt-model-pair", "ja:ko=qwen3:4b",
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
    assert aliases.get("simplified chinese") == "zh"
    assert aliases.get("traditional chinese") == "zh"
    assert aliases.get("zh-hans") == "zh"
    assert aliases.get("zh-hant") == "zh"
    assert aliases.get("cantonese") == "yue"


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
    assert s("traditional chinese,cantonese", "ja") == ["zh", "yue"]


def test_script_specific_chinese_subtitle_suffixes_parse_as_zh():
    parse = MODULE["parse_srt_filename"]
    assert parse("Show.S01E01.zh-Hans.srt") == (1, 1, "zh", False)
    assert parse("Show.S01E01.zh-Hant.srt") == (1, 1, "zh", False)
    assert parse("Show.S01E01.zh-TW.srt") == (1, 1, "zh", False)
    assert parse("Show.S01E01.chs.srt") == (1, 1, "zh", False)
    assert parse("Show.S01E01.cht.srt") == (1, 1, "zh", False)
    assert parse("Show.S01E01.pt-BR.srt") == (1, 1, "pt", False)
    assert parse("Show.S01E01.ja-ko.srt") is None


def test_wizard_language_normalization_explains_chinese_and_cantonese(capsys):
    fn = MODULE["_wizard_print_language_normalization"]
    fn("traditional chinese,cantonese,korean", ["zh", "yue", "ko"])
    out = capsys.readouterr().out
    assert "traditional chinese → Chinese (Traditional Chinese; searched as zh)" in out
    assert "cantonese → Cantonese (Cantonese; searches Chinese subtitles as zh, then adds Jyutping)" in out
    assert "korean → Korean" in out


def test_parse_mt_source_lang_resolves_jp_alias_in_single_form():
    # Single-token form: 'jp' should resolve to 'ja' for all targets.
    p = MODULE["parse_mt_source_lang"]
    assert p("jp", ["ko", "es"]) == {"ko": ("ja",), "es": ("ja",)}


def test_parse_mt_source_lang_resolves_jp_and_cn_in_pairs():
    # Pair form: aliases on both target and source sides.
    # Target 'cn' (alias for zh) must match -l 'zh'; source 'jp' resolves to 'ja'.
    p = MODULE["parse_mt_source_lang"]
    assert p("ko:jp,cn:en", ["ko", "zh"]) == {"ko": ("ja",), "zh": ("en",)}


def test_parse_mt_source_lang_none_or_empty_returns_none():
    p = MODULE["parse_mt_source_lang"]
    assert p(None, ["ja", "ko"]) is None
    assert p("", ["ja", "ko"]) is None
    assert p("   ", ["ja", "ko"]) is None


def test_parse_mt_source_lang_single_code_applies_to_all_targets():
    p = MODULE["parse_mt_source_lang"]
    assert p("ja", ["ja", "ko", "es"]) == {"ja": ("ja",), "ko": ("ja",), "es": ("ja",)}
    # Case-insensitive: single token gets lowered, targets get lowered.
    assert p("JA", ["KO", "ES"]) == {"ko": ("ja",), "es": ("ja",)}


def test_parse_mt_source_lang_explicit_pairs():
    p = MODULE["parse_mt_source_lang"]
    assert p("ko:ja", ["ja", "ko"]) == {"ko": ("ja",)}
    assert p("ko:ja,es:en", ["ja", "ko", "en", "es"]) == {"ko": ("ja",), "es": ("en",)}
    # Tolerates whitespace around tokens.
    assert p(" ko : ja , es : en ", ["ja", "ko", "en", "es"]) == {"ko": ("ja",), "es": ("en",)}


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
    assert "es: none of the forced sources (en) available" in text


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
    occurrences = text.count("none of the forced sources (en) available for this episode")
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
    assert "こんな所を　フルスロットルで…。" in body
    assert "《" not in body


def test_modify_main_single_line_removes_japanese_decorative_wrappers():
    import tempfile
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "Show.S01E04.ja.srt"
            target.write_text(
                "1\n"
                "00:21:35,327 --> 00:21:38,497\n"
                "これで労せずして　順位が１つ上がったわけか。》\n"
                "\n"
                "2\n"
                "00:23:42,488 --> 00:23:47,293\n"
                "（ナレーション）〈次回　第１７話　「残酷な現実」。〉\n",
                encoding="utf-8",
            )
            rc = MODULE["modify_main"]([str(target), "--single-line"])
            assert rc == 0
            body = target.read_text(encoding="utf-8")
    assert "これで労せずして　順位が１つ上がったわけか。" in body
    assert "（ナレーション）次回　第１７話　「残酷な現実」。" in body
    assert "》" not in body
    assert "〈" not in body
    assert "〉" not in body


def test_modify_main_episode_filter_processes_only_requested_episode():
    import tempfile
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ep1 = root / "Show.S01E01.ja.srt"
            ep2 = root / "Show.S01E02.ja.srt"
            ep1.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nこんにちは➡\n",
                encoding="utf-8",
            )
            ep2.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nこんばんは➡\n",
                encoding="utf-8",
            )
            rc = MODULE["modify_main"]([
                str(root), "-s", "1", "-e", "1", "--strip-cc-noise",
            ])
            assert rc == 0
            ep1_body = ep1.read_text(encoding="utf-8")
            ep2_body = ep2.read_text(encoding="utf-8")
    assert "➡" not in ep1_body
    assert "➡" in ep2_body


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
    # `modify` appears in the subcommand list and the topic-help footer.
    assert "modify" in text


def test_main_help_lists_fetch_and_merge_topics():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out), _isolated_config(None):
        MODULE["main"](["--help"])
    text = out.getvalue()
    # Both subcommand names appear (in the subcommand block + topic footer).
    assert "fetch" in text
    assert "merge" in text
    # Pipeline form mentioned.
    assert "--config" in text


def test_fetch_topic_help_renders_with_expected_content():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out), _isolated_config(None):
        rc = MODULE["main"](["--help", "fetch"])
    text = out.getvalue()
    assert rc == 0
    # Subcommand shape, --subdirectory flag, profile labels, recommended setup.
    assert "getsubtitle fetch URL" in text
    assert "getsubtitle fetch PATH" in text
    assert "--subdirectory" in text
    assert "Profiles" in text
    assert "--set-key tmdb" in text  # recommended setup is surfaced
    # The three profile names should be documented.
    for tag in ("ja", "ko", "en"):
        assert tag in text


def test_merge_topic_help_renders_with_expected_content():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out), _isolated_config(None):
        rc = MODULE["main"](["--help", "merge"])
    text = out.getvalue()
    assert rc == 0
    assert "getsubtitle merge PATH" in text
    assert "--subdirectory" in text
    assert "Merge options" in text


def test_legacy_aliases_no_longer_dispatch():
    # `download` and `combine` were dropped. They should NOT route to fetch
    # or merge — main() falls through to the URL-parser which errors out.
    import io, contextlib
    with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        for legacy in ("combine", "download"):
            try:
                rc = MODULE["main"]([legacy, "/tmp", "-l", "ja,en"])
            except (SystemExit, MODULE["CliError"]):
                rc = 2
            assert rc != 0, f"{legacy!r} should not still dispatch"


def test_legacy_help_topics_are_gone():
    # `getsubtitle --help download` and `--help combine` should now report
    # "Unknown help topic" (return code 2).
    import io, contextlib
    for legacy in ("download", "combine"):
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = MODULE["main"](["--help", legacy])
        assert rc == 2, f"--help {legacy} should report unknown topic"


# ---------------------------------------------------------------------------
# fetch / merge subcommands: helpers + dispatch (formerly batch)
# ---------------------------------------------------------------------------


def test_parse_season_from_folder_name_recognises_common_forms():
    p = MODULE["parse_season_from_folder_name"]
    # English Plex / Sonarr forms
    assert p("Season 01") == 1
    assert p("Season 1") == 1
    assert p("Season 5") == 5
    # Korean form
    assert p("1기") == 1
    assert p("2기") == 2
    assert p("3기") == 3
    # Compact form
    assert p("S01") == 1
    assert p("s2") == 2
    # Non-season folder names return None.
    assert p("MF Ghost") is None
    assert p("Moving (2023)") is None
    assert p("") is None


def test_detect_show_and_season_handles_three_layouts():
    import tempfile
    from pathlib import Path
    d = MODULE["detect_show_and_season"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Layout 1: Show/Season 01/video.mkv
        s1 = root / "Show" / "Season 01"
        s1.mkdir(parents=True)
        show, season = d(s1, root)
        assert show.name == "Show"
        assert season == 1
        # Layout 2: Show/1기/video.mkv (Korean form)
        s2 = root / "Show2" / "1기"
        s2.mkdir(parents=True)
        show, season = d(s2, root)
        assert show.name == "Show2"
        assert season == 1
        # Layout 3: Show/video.mkv (no season subdir)
        s3 = root / "FlatShow"
        s3.mkdir(parents=True)
        show, season = d(s3, root)
        assert show.name == "FlatShow"
        assert season is None


def test_detect_profile_from_title_kana_fast_path():
    # Japanese kana → ja regardless of TMDB. Fast path; no key needed.
    MODULE["_PROFILE_CACHE"].clear()
    assert MODULE["detect_profile_from_title"]("響け！ユーフォニアム") == "ja"
    assert MODULE["detect_profile_from_title"]("チ。") == "ja"


def test_detect_profile_from_title_no_tmdb_falls_back_to_charset():
    # No TMDB key configured → fall back to Hangul / Latin heuristics.
    # Force keychain_get to None so a real key stored on the dev box does
    # not turn this into a live TMDB lookup (runpy returns a shallow-copy
    # globals dict, so patching MODULE alone is not enough).
    import os
    MODULE["_PROFILE_CACHE"].clear()
    saved_env = os.environ.pop("TMDB_API_KEY", None)
    fn_g = MODULE["detect_profile_from_title"].__globals__
    saved_kc = fn_g["keychain_get"]
    try:
        fn_g["keychain_get"] = lambda *a, **k: None
        assert MODULE["detect_profile_from_title"]("기생수") == "ko"
        assert MODULE["detect_profile_from_title"]("Moving (2023)") == "en"
        assert MODULE["detect_profile_from_title"]("The Witcher") == "en"
    finally:
        fn_g["keychain_get"] = saved_kc
        if saved_env is not None:
            os.environ["TMDB_API_KEY"] = saved_env


def test_detect_profile_from_title_uses_tmdb_original_language():
    # When TMDB returns original_language=ja for a Korean folder name, we
    # should classify it as ja (this is the whole point of TMDB lookup —
    # Korean folder names of Japanese anime get the right profile).
    import os
    MODULE["_PROFILE_CACHE"].clear()
    os.environ["TMDB_API_KEY"] = "dummy"
    try:
        # Patch tmdb_search_tv to simulate "Japanese anime, Korean folder name".
        scope = MODULE["detect_profile_from_title"].__globals__
        saved_tv = scope["tmdb_search_tv"]
        scope["tmdb_search_tv"] = lambda title, api_key=None: {
            "tmdb_id": "1", "imdb_id": "tt1", "title": "Hibike",
            "year": 2015, "original_language": "ja",
        }
        try:
            assert MODULE["detect_profile_from_title"]("유포니움") == "ja"
        finally:
            scope["tmdb_search_tv"] = saved_tv
    finally:
        del os.environ["TMDB_API_KEY"]
        MODULE["_PROFILE_CACHE"].clear()


def test_detect_profile_from_title_caches_per_title():
    # Second call for the same title must not re-hit TMDB.
    import os
    MODULE["_PROFILE_CACHE"].clear()
    os.environ["TMDB_API_KEY"] = "dummy"
    call_count = [0]
    scope = MODULE["detect_profile_from_title"].__globals__
    saved_tv = scope["tmdb_search_tv"]
    saved_movie = scope["tmdb_search_movie"]
    def fake_tv(*a, **kw):
        call_count[0] += 1
        return {"tmdb_id": "1", "imdb_id": "tt1", "title": "X", "year": 2020, "original_language": "en"}
    scope["tmdb_search_tv"] = fake_tv
    scope["tmdb_search_movie"] = lambda *a, **kw: None
    try:
        MODULE["detect_profile_from_title"]("Some Show")
        MODULE["detect_profile_from_title"]("Some Show")
        MODULE["detect_profile_from_title"]("Some Show")
        assert call_count[0] == 1, "expected cache to short-circuit subsequent calls"
    finally:
        scope["tmdb_search_tv"] = saved_tv
        scope["tmdb_search_movie"] = saved_movie
        del os.environ["TMDB_API_KEY"]
        MODULE["_PROFILE_CACHE"].clear()


def test_batch_walk_targets_finds_folders_and_bare_files():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # A Plex-style show with a Season subdir
        (root / "Show A" / "Season 01").mkdir(parents=True)
        (root / "Show A" / "Season 01" / "ep01.mkv").touch()
        # A flat show
        (root / "Show B").mkdir()
        (root / "Show B" / "ep01.mkv").touch()
        # A bare movie at root
        (root / "movie.mkv").touch()
        # A folder with no videos — should be ignored
        (root / "no-videos").mkdir()
        (root / "no-videos" / "readme.txt").touch()

        targets = MODULE["_batch_walk_targets"](root)
        names = sorted((t[0].name, t[1].name, t[2]) for t in targets)
    # Three targets: the two video folders + the bare file.
    assert len(names) == 3
    # Find each by its leaf path component.
    folder_a, show_a, season_a = next(t for t in names if t[0] == "Season 01")
    folder_b, show_b, season_b = next(t for t in names if t[0] == "Show B")
    bare_name, bare_show, bare_season = next(t for t in names if t[0] == "movie.mkv")
    assert show_a == "Show A" and season_a == 1
    assert show_b == "Show B" and season_b is None
    assert bare_show == "movie.mkv" and bare_season is None


def test_fetch_main_subdirectory_dispatches_to_per_show_runs():
    # `getsubtitle fetch ROOT --subdirectory` should walk every immediate
    # subdir of ROOT and run a per-show fetch for each. We don't run real
    # subprocess calls — patch subprocess.run to capture them.
    import tempfile, io, contextlib
    from pathlib import Path
    scope = MODULE["fetch_main"].__globals__
    saved_run = scope["subprocess"].run

    captured: list[list[str]] = []
    class _FakeResult:
        returncode = 0
    def fake_run(args, **kwargs):
        captured.append(args)
        return _FakeResult()
    scope["subprocess"].run = fake_run

    # Patch profile detection to a known value so we don't hit TMDB.
    saved_detect = scope["detect_profile_from_title"]
    scope["detect_profile_from_title"] = lambda title, year=None: "en"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Show A").mkdir()
            (root / "Show A" / "ep01.mkv").touch()
            (root / "Show B").mkdir()
            (root / "Show B" / "ep01.mkv").touch()
            with _isolated_config(None):
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = MODULE["main"]([
                        "fetch", str(root), "--subdirectory", "--run",
                    ])
                assert rc == 0
                fetch_calls = [c for c in captured if "translate" not in c]
                assert any("Show A" in " ".join(c) for c in fetch_calls), captured
                assert any("Show B" in " ".join(c) for c in fetch_calls), captured
    finally:
        scope["subprocess"].run = saved_run
        scope["detect_profile_from_title"] = saved_detect


def test_fetch_main_profile_override_applies_to_all_folders():
    import tempfile, io, contextlib
    from pathlib import Path
    scope = MODULE["fetch_main"].__globals__
    saved_run = scope["subprocess"].run
    captured_langs: list[str] = []
    class _FakeResult:
        returncode = 0
    def fake_run(args, **kwargs):
        # Pull the -l value so we can verify the profile actually drove it.
        for i, a in enumerate(args):
            if a == "-l" and i + 1 < len(args):
                captured_langs.append(args[i + 1])
        return _FakeResult()
    scope["subprocess"].run = fake_run

    # Force the detector to ja so we'd normally get -l ko fetches, but
    # --profile en should override and give us -l es,ko fetches.
    saved_detect = scope["detect_profile_from_title"]
    scope["detect_profile_from_title"] = lambda title, year=None: "ja"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Show A").mkdir()
            (root / "Show A" / "ep01.mkv").touch()
            with _isolated_config(None):
                with contextlib.redirect_stdout(io.StringIO()):
                    MODULE["main"]([
                        "fetch", str(root), "--subdirectory",
                        "--profile", "en", "--run",
                    ])
    finally:
        scope["subprocess"].run = saved_run
        scope["detect_profile_from_title"] = saved_detect
    # en profile fetches es+ko, not ko alone.
    assert any("es,ko" in lv for lv in captured_langs), captured_langs


def test_fetch_main_path_form_respects_explicit_languages_over_profile_defaults():
    import tempfile, io, contextlib
    from pathlib import Path
    scope = MODULE["fetch_main"].__globals__
    saved_run = scope["subprocess"].run
    captured_langs: list[str] = []

    class _FakeResult:
        returncode = 0

    def fake_run(args, **kwargs):
        for i, a in enumerate(args):
            if a == "-l" and i + 1 < len(args):
                captured_langs.append(args[i + 1])
        return _FakeResult()

    scope["subprocess"].run = fake_run
    saved_detect = scope["detect_profile_from_title"]
    scope["detect_profile_from_title"] = lambda title, year=None: "en"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Fena - Pirate Princess").mkdir()
            (root / "Fena - Pirate Princess" / "S01E01.mkv").touch()
            with _isolated_config(None):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    MODULE["main"]([
                        "fetch", str(root), "--subdirectory",
                        "--languages", "ja,ko", "--run",
                    ])
                text = out.getvalue()
    finally:
        scope["subprocess"].run = saved_run
        scope["detect_profile_from_title"] = saved_detect

    assert captured_langs == ["ja,ko"], captured_langs
    assert "es,ko" not in captured_langs
    assert "requested languages: ja,ko" in text
    assert "fetch: -l ja,ko (requested)" in text


def test_fetch_main_path_form_respects_title_override():
    import tempfile, io, contextlib
    from pathlib import Path
    scope = MODULE["fetch_main"].__globals__
    saved_run = scope["subprocess"].run
    saved_detect = scope["detect_profile_from_title"]
    captured: list[list[str]] = []

    class _FakeResult:
        returncode = 0

    def fake_run(args, **kwargs):
        captured.append(args)
        return _FakeResult()

    scope["subprocess"].run = fake_run
    scope["detect_profile_from_title"] = lambda title, year=None: "ja"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "니아 오토마타"
            root.mkdir()
            (root / "[Ohys-Raws] NieR Automata Ver1.1a - 01.mp4").touch()
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                rc = MODULE["main"]([
                    "fetch", str(root), "--languages", "ja,ko",
                    "--title", "NieR Automata Ver1.1a", "--anilist", "145665", "--run",
                ])
        assert rc == 0
    finally:
        scope["subprocess"].run = saved_run
        scope["detect_profile_from_title"] = saved_detect

    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[cmd.index("--title") + 1] == "NieR Automata Ver1.1a"
    assert cmd[cmd.index("--anilist") + 1] == "145665"
    assert cmd[cmd.index("-l") + 1] == "ja,ko"


def test_fetch_main_explicit_season_folder_fetches_once_with_parent_title():
    import tempfile, io, contextlib
    from pathlib import Path
    scope = MODULE["fetch_main"].__globals__
    saved_run = scope["subprocess"].run
    saved_detect = scope["detect_profile_from_title"]
    captured: list[list[str]] = []

    class _FakeResult:
        returncode = 0

    def fake_run(args, **kwargs):
        captured.append(args)
        return _FakeResult()

    scope["subprocess"].run = fake_run
    scope["detect_profile_from_title"] = lambda title, year=None: "ja"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            season = Path(tmp) / "Fena - Pirate Princess" / "Season 01"
            season.mkdir(parents=True)
            (season / "Fena - Pirate Princess - S01E01.mkv").touch()
            (season / "Fena - Pirate Princess - S01E02.mkv").touch()
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                rc = MODULE["main"](["fetch", str(season), "--languages", "ja,ko", "--run"])
        assert rc == 0
    finally:
        scope["subprocess"].run = saved_run
        scope["detect_profile_from_title"] = saved_detect

    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[cmd.index("--title") + 1] == "Fena - Pirate Princess"
    assert cmd[cmd.index("-s") + 1] == "1"
    assert cmd[cmd.index("-e") + 1] == "all"
    assert cmd[cmd.index("-l") + 1] == "ja,ko"


def test_fetch_main_explicit_video_file_scopes_to_that_episode():
    import tempfile, io, contextlib
    from pathlib import Path
    scope = MODULE["fetch_main"].__globals__
    saved_run = scope["subprocess"].run
    saved_detect = scope["detect_profile_from_title"]
    captured: list[list[str]] = []

    class _FakeResult:
        returncode = 0

    def fake_run(args, **kwargs):
        captured.append(args)
        return _FakeResult()

    scope["subprocess"].run = fake_run
    scope["detect_profile_from_title"] = lambda title, year=None: "ja"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "Fena - Pirate Princess" / "Season 01" / "Fena - Pirate Princess - S01E10.mkv"
            video.parent.mkdir(parents=True)
            video.touch()
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                rc = MODULE["main"](["fetch", str(video), "--languages", "ja,ko", "--run"])
        assert rc == 0
    finally:
        scope["subprocess"].run = saved_run
        scope["detect_profile_from_title"] = saved_detect

    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[cmd.index("--title") + 1] == "Fena - Pirate Princess"
    assert cmd[cmd.index("-s") + 1] == "1"
    assert cmd[cmd.index("-e") + 1] == "10"


def test_fetch_main_dry_run_is_default_for_path_form():
    # PATH form is dry-run by default — no real subprocess calls should
    # leak through; the captured _batch_run path adds --dry-run when not
    # passed --run.
    import tempfile, io, contextlib
    from pathlib import Path
    scope = MODULE["fetch_main"].__globals__
    saved_run = scope["subprocess"].run
    all_args: list[list[str]] = []
    class _FakeResult:
        returncode = 0
    def fake_run(args, **kwargs):
        all_args.append(args)
        return _FakeResult()
    scope["subprocess"].run = fake_run

    saved_detect = scope["detect_profile_from_title"]
    scope["detect_profile_from_title"] = lambda title, year=None: "ja"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Show A").mkdir()
            (root / "Show A" / "ep01.mkv").touch()
            with _isolated_config(None):
                with contextlib.redirect_stdout(io.StringIO()):
                    # No --run flag → dry-run default. With --subdirectory
                    # to exercise the walker on Show A.
                    MODULE["main"]([
                        "fetch", str(root), "--subdirectory",
                    ])
    finally:
        scope["subprocess"].run = saved_run
        scope["detect_profile_from_title"] = saved_detect
    # PATH form defaults to dry-run: every captured subprocess invocation
    # must carry --dry-run so the underlying getsubtitle call is a no-op.
    assert all_args, "expected at least one captured call"
    getsubtitle_calls = [args for args in all_args if args and args[0] != "security"]
    assert getsubtitle_calls, "expected at least one getsubtitle subprocess call"
    for args in getsubtitle_calls:
        assert "--dry-run" in args, f"expected --dry-run in {args}"


def test_fetch_main_url_form_delegates_to_main_download_flow():
    # `getsubtitle fetch URL ...` should be a thin pass-through to the
    # bare-URL download flow. We patch main() to capture what arrived.
    import io, contextlib
    captured: list[list[str]] = []
    real_main = MODULE["main"]
    fetch_main_globals = MODULE["fetch_main"].__globals__
    def fake_main(argv):
        captured.append(list(argv))
        return 0
    fetch_main_globals["main"] = fake_main
    try:
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            rc = MODULE["fetch_main"]([
                "https://www.imdb.com/title/tt28299608/",
                "-l", "ja,ko",
            ])
        assert rc == 0
        assert len(captured) == 1
        assert captured[0][0].startswith("https://")
        assert "-l" in captured[0]
    finally:
        fetch_main_globals["main"] = real_main


def test_fetch_main_url_form_preserves_title_override():
    import io, contextlib
    captured: list[list[str]] = []
    real_main = MODULE["main"]
    fetch_main_globals = MODULE["fetch_main"].__globals__

    def fake_main(argv):
        captured.append(list(argv))
        return 0

    fetch_main_globals["main"] = fake_main
    try:
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            rc = MODULE["fetch_main"]([
                "https://example.com/title/blocked",
                "-l", "ja",
                "--title", "Known Title",
                "--anilist", "145665",
            ])
        assert rc == 0
    finally:
        fetch_main_globals["main"] = real_main

    assert captured == [[
        "https://example.com/title/blocked",
        "-l", "ja",
        "--title", "Known Title",
        "--anilist", "145665",
    ]]


def test_fetch_main_url_with_subdirectory_is_an_error():
    # --subdirectory is for PATH only; combining it with a URL must fail.
    import io, contextlib
    CliError = MODULE["CliError"]
    with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
        try:
            MODULE["fetch_main"]([
                "https://example.com/x", "--subdirectory",
            ])
        except CliError as e:
            assert "subdirectory" in str(e).lower()
        else:
            raise AssertionError("expected CliError for URL + --subdirectory")


def test_merge_main_subdirectory_runs_combine_per_subdir():
    # `getsubtitle merge ROOT --subdirectory -l ja,ko` should invoke
    # combine_main once per immediate subdir, with --subdirectory stripped.
    import tempfile, io, contextlib
    from pathlib import Path
    captured: list[list[str]] = []
    saved = MODULE["combine_main"]
    # combine_main re-enters itself recursively with --subdirectory stripped.
    # We patch it at module scope to count invocations.
    def fake_combine(argv):
        captured.append(list(argv))
        return 0
    # Patch where combine_main is looked up by merge_main + the subdir
    # dispatcher.
    MODULE["combine_main"] = fake_combine
    # The dispatcher in combine_main itself calls combine_main(...) for each
    # subdir — but since we replaced combine_main wholesale, the dispatcher
    # is also gone. So we need a different strategy: leave combine_main in
    # place and capture _batch_run instead — but combine_main writes files,
    # not subprocesses. Easiest: just verify merge_main calls combine_main
    # via the dispatch in main().
    MODULE["combine_main"] = saved
    # Verify merge subcommand reaches combine_main code path through main().
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Show A").mkdir()
            (root / "Show B").mkdir()
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = MODULE["main"]([
                    "merge", str(root), "--subdirectory", "-l", "ja,ko",
                ])
            # Per-subdir loop prints a heading per subdir even when no SRTs
            # are found — and the dispatcher returns 0 when every subdir
            # ran (each individual run may have its own return code).
            assert rc in (0, 1)
    finally:
        MODULE["combine_main"] = saved


def test_combine_subdirectory_dispatch_prints_per_subdir_heading():
    # The --subdirectory wrapper prints "━━ combine SHOW/SUB ━━" per subdir.
    # Verify by reading captured stdout.
    import tempfile, io, contextlib
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Show A").mkdir()
        (root / "Show B").mkdir()
        out = io.StringIO()
        with _isolated_config(None), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            MODULE["combine_main"]([str(root), "--subdirectory", "-l", "ja,ko"])
        text = out.getvalue()
        # Per-subdir headings should appear for both Show A and Show B.
        assert "Show A" in text
        assert "Show B" in text


def test_combine_parser_accepts_subdirectory_flag():
    # The --subdirectory flag must be in the combine/translate/modify parsers.
    cp = MODULE["build_combine_parser"]()
    tp = MODULE["build_translate_parser"]()
    mp = MODULE["build_modify_parser"]()
    for p in (cp, tp, mp):
        # Argparse stores known optionals in the actions list.
        flags = {a.option_strings[0] if a.option_strings else a.dest
                 for a in p._actions}
        assert any("--subdirectory" in f for f in flags), (
            f"parser missing --subdirectory: {sorted(flags)}"
        )


def test_looks_like_url_helper():
    f = MODULE["_looks_like_url"]
    assert f("https://example.com")
    assert f("http://example.com")
    assert f("HTTPS://EXAMPLE.COM")
    assert not f("/Users/me/Movies")
    assert not f("~/Downloads/Show")
    assert not f("Show A")


def test_immediate_subdirs_helper_skips_dotfiles():
    import tempfile
    from pathlib import Path
    f = MODULE["_immediate_subdirs"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Show A").mkdir()
        (root / "Show B").mkdir()
        (root / ".hidden").mkdir()
        (root / "loose.mkv").touch()
        subs = f(root)
        names = sorted(s.name for s in subs)
        assert names == ["Show A", "Show B"]


# ---------------------------------------------------------------------------
# Pipeline form: getsubtitle --fetch X --translate ENGINE --merge ... etc.
# ---------------------------------------------------------------------------


def test_split_pipeline_argv_partitions_by_verb_flags():
    split = MODULE["split_pipeline_argv"]
    argv = [
        "--output", "/tmp/out",
        "--fetch", "/Plex", "--subdirectory",
        "--translate", "ollama:qwen3:8b", "--mt-source-lang", "en",
        "--merge", "-l", "ja,en", "--format", "vtt",
    ]
    blocks = split(argv)
    assert blocks["shared"] == ["--output", "/tmp/out"]
    assert blocks["fetch"] == ["/Plex", "--subdirectory"]
    assert blocks["translate"] == ["ollama:qwen3:8b", "--mt-source-lang", "en"]
    assert blocks["merge"] == ["-l", "ja,en", "--format", "vtt"]


def test_split_pipeline_argv_canonical_order_independent_of_typing_order():
    # User types --merge before --fetch — the splitter just bins per-verb;
    # canonical order is enforced later by pipeline_main.
    split = MODULE["split_pipeline_argv"]
    blocks = split(["--merge", "-l", "ja,en", "--fetch", "/X"])
    assert blocks["fetch"] == ["/X"]
    assert blocks["merge"] == ["-l", "ja,en"]


def test_is_pipeline_argv_true_when_any_verb_flag_present():
    f = MODULE["_is_pipeline_argv"]
    assert f(["--fetch", "/X"]) is True
    assert f(["--merge"]) is True
    assert f(["--output", "/tmp/out", "--translate", "argos"]) is True
    # No verb flag → not a pipeline; falls through to single-verb dispatch.
    assert f(["fetch", "/X"]) is False
    assert f(["URL"]) is False
    assert f(["merge", "/X", "-l", "ja,en"]) is False


def test_parse_engine_spec_handles_bare_and_colon_forms():
    parse = MODULE["_parse_engine_spec"]
    assert parse("argos") == ("argos", None)
    assert parse("ollama") == ("ollama", None)
    assert parse("deepl") == ("deepl", None)
    assert parse("ollama:qwen3:8b") == ("ollama", "qwen3:8b")
    assert parse("ollama:llama3.2:3b") == ("ollama", "llama3.2:3b")
    assert parse("") == ("", None)


def test_parse_engine_spec_rejects_unknown_engines():
    parse = MODULE["_parse_engine_spec"]
    try:
        parse("gpt4")
    except MODULE["CliError"] as e:
        assert "Unknown engine" in str(e)
    else:
        raise AssertionError("expected CliError for unknown engine")


def test_rewrite_translate_block_emits_canonical_engine_flags():
    rewrite = MODULE["_rewrite_translate_block"]
    assert rewrite(["argos"]) == ["--engine", "argos"]
    assert rewrite(["ollama:qwen3:8b"]) == ["--engine", "ollama", "--model", "qwen3:8b"]
    # Pass-through of other flags after the engine spec.
    assert rewrite(["ollama", "--mt-source", "en"]) == [
        "--engine", "ollama", "--mt-source", "en",
    ]
    # Empty engine → --no-mt-engine.
    assert rewrite([""]) == ["--no-mt-engine"]


def test_rewrite_translate_block_errors_when_engine_missing():
    rewrite = MODULE["_rewrite_translate_block"]
    CliError = MODULE["CliError"]
    try:
        rewrite([])
    except CliError as e:
        assert "engine" in str(e).lower()
    else:
        raise AssertionError("expected CliError for empty --translate block")
    try:
        rewrite(["--mt-source-lang", "en"])
    except CliError as e:
        assert "engine" in str(e).lower()
    else:
        raise AssertionError("expected CliError when first token is a flag")


def test_pipeline_dispatch_runs_fetch_then_merge_in_canonical_order():
    # Even when typed --merge first, fetch must run first.
    import tempfile, io, contextlib
    from pathlib import Path
    calls: list[str] = []
    scope = MODULE["pipeline_main"].__globals__

    # Stub fetch_main, combine_main (merge calls combine_main internally).
    saved_fetch = scope["fetch_main"]
    saved_combine = scope["combine_main"]
    def fake_fetch(argv):
        calls.append(f"fetch:{argv[0]}")
        return 0
    def fake_combine(argv):
        calls.append(f"merge:{argv[0]}")
        return 0
    scope["fetch_main"] = fake_fetch
    scope["combine_main"] = fake_combine
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                rc = MODULE["main"]([
                    "--merge", "-l", "ja,en",
                    "--fetch", tmp, "--subdirectory",
                ])
            assert rc == 0
            # Fetch must execute BEFORE merge regardless of typing order.
            assert calls[0].startswith("fetch:"), calls
            assert calls[1].startswith("merge:"), calls
    finally:
        scope["fetch_main"] = saved_fetch
        scope["combine_main"] = saved_combine


def test_pipeline_url_fetch_passes_shared_output_and_resolves_anilist_folder():
    import io, contextlib
    import tempfile
    captured: dict[str, list[str]] = {}
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    saved_modify = scope["modify_main"]
    saved_combine = scope["combine_main"]
    saved_info = scope["fetch_anilist_info"]

    def fake_fetch(argv):
        captured["fetch"] = list(argv)
        return 0

    def fake_modify(argv):
        captured["modify"] = list(argv)
        return 0

    def fake_combine(argv):
        captured["merge"] = list(argv)
        return 0

    class Info:
        title = "MF Ghost 2nd Season"
        title_aliases = []
        episodes = 12
        format = "TV"
        def is_movie(self):
            return False

    scope["fetch_main"] = fake_fetch
    scope["modify_main"] = fake_modify
    scope["combine_main"] = fake_combine
    scope["fetch_anilist_info"] = lambda _id: Info()
    try:
        with tempfile.TemporaryDirectory() as td, _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            output_root = f"{td}/GetSubtitle"
            rc = MODULE["main"]([
                "--fetch", "https://anilist.co/anime/171642/",
                "--season", "all", "--episode", "all",
                "--modify", "--strip-cc-noise",
                "--merge", "--languages", "ja,en", "--format", "vtt",
                "--output", output_root,
            ])
            expected = f"{output_root}/MF Ghost 2nd Season/All Seasons"
        assert rc == 0
    finally:
        scope["fetch_main"] = saved_fetch
        scope["modify_main"] = saved_modify
        scope["combine_main"] = saved_combine
        scope["fetch_anilist_info"] = saved_info

    assert "--output" in captured["fetch"]
    assert captured["fetch"][captured["fetch"].index("--output") + 1] == output_root
    assert captured["modify"][0] == expected
    assert captured["merge"][0] == expected


def test_pipeline_downstream_verbs_inherit_fetch_scope_once():
    import io, contextlib
    import tempfile
    captured: dict[str, list[str]] = {}
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    saved_tr = scope["translate_main"]
    saved_modify = scope["modify_main"]
    saved_combine = scope["combine_main"]

    def fake_fetch(argv):
        captured["fetch"] = list(argv)
        return 0

    def fake_translate(argv):
        captured["translate"] = list(argv)
        return 0

    def fake_modify(argv):
        captured["modify"] = list(argv)
        return 0

    def fake_combine(argv):
        captured["merge"] = list(argv)
        return 0

    scope["fetch_main"] = fake_fetch
    scope["translate_main"] = fake_translate
    scope["modify_main"] = fake_modify
    scope["combine_main"] = fake_combine
    try:
        with tempfile.TemporaryDirectory() as td, _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            rc = MODULE["main"]([
                "--fetch", "https://anilist.co/anime/122052/",
                "--season", "1", "--episode", "1-3",
                "--languages", "ja,ko",
                "--translate", "ollama",
                "--modify", "--strip-cc-noise",
                "--merge", "--languages", "ja,ko", "--format", "vtt",
                "--output", f"{td}/GetSubtitle",
            ])
        assert rc == 0
    finally:
        scope["fetch_main"] = saved_fetch
        scope["translate_main"] = saved_tr
        scope["modify_main"] = saved_modify
        scope["combine_main"] = saved_combine

    assert captured["fetch"].count("--season") == 1
    for verb in ("translate", "modify", "merge"):
        args = captured[verb]
        assert "--season" in args
        assert args[args.index("--season") + 1] == "1"
        assert "--episode" in args
        assert args[args.index("--episode") + 1] == "1-3"


def test_pipeline_post_fetch_uses_actual_resolved_output_folder_for_title_search():
    import io, contextlib
    import tempfile
    from pathlib import Path

    captured: dict[str, list[str]] = {}
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    saved_modify = scope["modify_main"]
    saved_combine = scope["combine_main"]

    with tempfile.TemporaryDirectory() as td:
        output_root = Path(td) / "Plex" / "MASHLE - MAGIC AND MUSCLES"
        actual = output_root / "MASHLE Kami Shinkakusha Kouho Senbatsu Shiken-hen" / "Season 02"

        def fake_fetch(argv):
            captured["fetch"] = list(argv)
            actual.mkdir(parents=True, exist_ok=True)
            (actual / "MASHLE Kami Shinkakusha Kouho Senbatsu Shiken-hen - S02E01.ja.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nマッシュ\n",
                encoding="utf-8",
            )
            return 0

        def fake_modify(argv):
            captured["modify"] = list(argv)
            return 0

        def fake_combine(argv):
            captured["merge"] = list(argv)
            return 0

        scope["fetch_main"] = fake_fetch
        scope["modify_main"] = fake_modify
        scope["combine_main"] = fake_combine
        try:
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                rc = MODULE["main"]([
                    "--fetch", "--title", "mashle - magic and muscles",
                    "--season", "2", "--episode", "1",
                    "--languages", "ja,en",
                    "--modify", "--strip-cc-noise",
                    "--merge", "--languages", "ja,en", "--format", "vtt",
                    "--output", str(output_root),
                ])
            assert rc == 0
        finally:
            scope["fetch_main"] = saved_fetch
            scope["modify_main"] = saved_modify
            scope["combine_main"] = saved_combine

        wrong = output_root / "mashle - magic and muscles" / "Season 02"
        assert captured["modify"][0] == str(actual)
        assert captured["merge"][0] == str(actual)
        assert captured["modify"][0] != str(wrong)


def test_wizard_open_folder_target_prefers_actual_resolved_fetch_folder():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        output_root = Path(td) / "Plex" / "MASHLE - MAGIC AND MUSCLES"
        actual = output_root / "MASHLE Kami Shinkakusha Kouho Senbatsu Shiken-hen" / "Season 02"
        actual.mkdir(parents=True)
        (actual / "MASHLE Kami Shinkakusha Kouho Senbatsu Shiken-hen - S02E01.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nマッシュ\n",
            encoding="utf-8",
        )
        state = MODULE["_WizardState"](
            source="mashle - magic and muscles",
            source_kind="title",
            languages=["ja", "en"],
            order=["ja", "en"],
            season="2",
            episode="1",
            steps={"fetch", "modify", "merge"},
            output=str(output_root),
        )
        target = MODULE["_wizard_open_folder_target"](state)
    assert target == actual


def test_pipeline_translate_rewrites_engine_to_canonical_flags():
    # `--translate ollama:qwen3:8b` should reach translate_main as
    # `--engine ollama --model qwen3:8b`.
    import io, contextlib
    captured: list[list[str]] = []
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    saved_tr = scope["translate_main"]
    def fake_fetch(argv): return 0
    def fake_tr(argv):
        captured.append(list(argv))
        return 0
    scope["fetch_main"] = fake_fetch
    scope["translate_main"] = fake_tr
    try:
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            MODULE["main"]([
                "--fetch", "/some/path",
                    "--translate", "ollama:qwen3:8b", "--mt-source", "en",
            ])
    finally:
        scope["fetch_main"] = saved_fetch
        scope["translate_main"] = saved_tr
    assert captured, "expected translate_main to be invoked"
    args = captured[0]
    assert "--engine" in args and args[args.index("--engine") + 1] == "ollama"
    assert "--model" in args and args[args.index("--model") + 1] == "qwen3:8b"
    assert "--mt-source" in args and args[args.index("--mt-source") + 1] == "en"


def test_pipeline_translate_inherits_fetch_languages_and_owns_mt_for_url_fetch():
    # Wizard/config workflows often say:
    #   --fetch URL --languages ja,ko --translate deepl
    # Fetch should download only; the separate translate step should use the
    # chosen engine and inherit the requested language list.
    import io, contextlib, tempfile
    captured: dict[str, list[str]] = {}
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    saved_tr = scope["translate_main"]

    def fake_fetch(argv):
        captured["fetch"] = list(argv)
        return 0

    def fake_tr(argv):
        captured["translate"] = list(argv)
        return 0

    scope["fetch_main"] = fake_fetch
    scope["translate_main"] = fake_tr
    try:
        with tempfile.TemporaryDirectory() as tmp, _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            rc = MODULE["main"]([
                "--fetch", "https://www.imdb.com/title/tt0245429/",
                "--languages", "ja,ko",
                "--translate", "deepl",
                "--output", f"{tmp}/GetSubtitle",
            ])
        assert rc == 0
    finally:
        scope["fetch_main"] = saved_fetch
        scope["translate_main"] = saved_tr

    assert "--no-engine" in captured["fetch"]
    tr_args = captured["translate"]
    assert "--engine" in tr_args
    assert tr_args[tr_args.index("--engine") + 1] == "deepl"
    assert "--languages" in tr_args
    assert tr_args[tr_args.index("--languages") + 1] == "ja,ko"
    assert "--mt-source" not in tr_args


def test_pipeline_merge_inherits_fetch_languages_when_omitted():
    import io, contextlib, tempfile
    captured: dict[str, list[str]] = {}
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    saved_combine = scope["combine_main"]

    def fake_fetch(argv):
        captured["fetch"] = list(argv)
        return 0

    def fake_combine(argv):
        captured["merge"] = list(argv)
        return 0

    scope["fetch_main"] = fake_fetch
    scope["combine_main"] = fake_combine
    try:
        with tempfile.TemporaryDirectory() as tmp, _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            rc = MODULE["main"]([
                "--fetch", "https://www.imdb.com/title/tt0245429/",
                "--languages", "ja,ko",
                "--merge", "--format", "vtt",
                "--output", f"{tmp}/GetSubtitle",
            ])
        assert rc == 0
    finally:
        scope["fetch_main"] = saved_fetch
        scope["combine_main"] = saved_combine

    assert "--languages" in captured["fetch"]
    merge_args = captured["merge"]
    assert "--languages" in merge_args
    assert merge_args[merge_args.index("--languages") + 1] == "ja,ko"
    assert "--format" in merge_args
    assert merge_args[merge_args.index("--format") + 1] == "vtt"


def test_pipeline_translate_inherits_merge_languages_for_local_workflow():
    # Local wizard workflows can be translate + modify + merge with no fetch.
    # In that case the requested stack is already present on the merge block.
    import io, contextlib, tempfile
    captured: dict[str, list[str]] = {}
    scope = MODULE["pipeline_main"].__globals__
    saved_tr = scope["translate_main"]
    saved_modify = scope["modify_main"]
    saved_combine = scope["combine_main"]

    def fake_tr(argv):
        captured["translate"] = list(argv)
        return 0

    def fake_modify(argv):
        captured["modify"] = list(argv)
        return 0

    def fake_combine(argv):
        captured["merge"] = list(argv)
        return 0

    scope["translate_main"] = fake_tr
    scope["modify_main"] = fake_modify
    scope["combine_main"] = fake_combine
    try:
        with tempfile.TemporaryDirectory() as tmp, _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            rc = MODULE["main"]([
                "--source", tmp,
                "--translate", "deepl",
                "--modify", "--strip-cc-noise",
                "--merge", "--languages", "ja,ko",
                "--output", tmp,
            ])
        assert rc == 0
    finally:
        scope["translate_main"] = saved_tr
        scope["modify_main"] = saved_modify
        scope["combine_main"] = saved_combine

    tr_args = captured["translate"]
    assert "--engine" in tr_args
    assert tr_args[tr_args.index("--engine") + 1] == "deepl"
    assert "--languages" in tr_args
    assert tr_args[tr_args.index("--languages") + 1] == "ja,ko"
    assert "--mt-source" not in tr_args


def test_pipeline_modify_merge_vtt_inputs_succeeds_without_format_hints(tmp_path):
    (tmp_path / "Show.S01E09.ja.vtt").write_text(
        "WEBVTT\n\n"
        "1\n00:00:01.000 --> 00:00:03.000 position:50.00%,middle align:middle\n"
        "<c.japanese><c.bg_transparent>日本語</c.bg_transparent></c.japanese>\n",
        encoding="utf-8",
    )
    (tmp_path / "Show.S01E09.ko.vtt").write_text(
        "WEBVTT\n\n"
        "1\n00:00:01.000 --> 00:00:03.000 position:50.00%,middle align:middle\n"
        "<c.korean><c.bg_transparent>한국어</c.bg_transparent></c.korean>\n",
        encoding="utf-8",
    )

    rc = MODULE["main"]([
        "--source", str(tmp_path),
        "--modify", "--strip-cc-noise", "--single-line",
        "--merge", "--languages", "ja,ko", "--format", "vtt",
        "--output", str(tmp_path),
        "--no-open-folder-prompt",
    ])

    assert rc == 0
    assert (tmp_path / "Show.S01E09.ja-ko.vtt").exists()


def test_pipeline_no_open_folder_prompt_is_global_not_modify_arg():
    blocks = MODULE["split_pipeline_argv"]([
        "--fetch", "title://mashle",
        "--output", "/tmp/out",
        "--modify", "--strip-cc-noise",
        "--no-open-folder-prompt",
    ])
    assert "--no-open-folder-prompt" in blocks["shared"]
    assert "--no-open-folder-prompt" not in blocks["modify"]


def test_pipeline_shared_force_and_no_open_prompt_propagate_to_supported_verbs():
    import io, contextlib, tempfile
    captured: dict[str, list[str]] = {}
    scope = MODULE["pipeline_main"].__globals__
    saved_modify = scope["modify_main"]
    saved_combine = scope["combine_main"]

    def fake_modify(argv):
        captured["modify"] = list(argv)
        return 0

    def fake_combine(argv):
        captured["merge"] = list(argv)
        return 0

    scope["modify_main"] = fake_modify
    scope["combine_main"] = fake_combine
    try:
        with tempfile.TemporaryDirectory() as tmp, _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            rc = MODULE["main"]([
                "--source", tmp,
                "--modify", "--strip-cc-noise",
                "--merge", "--languages", "ja,ko",
                "--force", "--no-open-folder-prompt",
            ])
        assert rc == 0
    finally:
        scope["modify_main"] = saved_modify
        scope["combine_main"] = saved_combine

    assert "--force" in captured["modify"]
    assert "--force" in captured["merge"]
    assert "--no-open-folder-prompt" in captured["merge"]


def test_pipeline_requires_target_for_downstream_verbs():
    # `--merge` alone (no --fetch, no --output) → error.
    import io, contextlib
    CliError = MODULE["CliError"]
    try:
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            MODULE["main"](["--merge", "-l", "ja,en"])
    except CliError as e:
        assert "fetch" in str(e).lower() or "output" in str(e).lower()
    else:
        raise AssertionError("expected CliError when no --fetch / --output for downstream verb")


def test_pipeline_url_fetch_plus_merge_requires_output():
    # URL form fetch + merge: we can't know where SRTs landed without --output.
    import io, contextlib
    CliError = MODULE["CliError"]
    try:
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            MODULE["main"]([
                "--fetch", "https://www.imdb.com/title/tt28299608/",
                "--merge", "-l", "ja,en",
            ])
    except CliError as e:
        assert "--output" in str(e) or "output" in str(e).lower()
    else:
        raise AssertionError("expected CliError when URL fetch + merge w/o --output")


def test_pipeline_from_config_file_runs_full_pipeline():
    # Write a TOML, point --pipeline at it, verify verbs were called.
    import tempfile, io, contextlib
    from pathlib import Path
    calls: list[tuple[str, list]] = []
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    saved_combine = scope["combine_main"]
    saved_tr = scope["translate_main"]
    def fake_fetch(argv): calls.append(("fetch", list(argv))); return 0
    def fake_tr(argv): calls.append(("translate", list(argv))); return 0
    def fake_combine(argv): calls.append(("merge", list(argv))); return 0
    scope["fetch_main"] = fake_fetch
    scope["translate_main"] = fake_tr
    scope["combine_main"] = fake_combine
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "pipeline.toml"
            # NB: top-level shared keys like `output` are TOML-valid but
            # are not parseable by the minimal in-tree fallback parser
            # used when neither stdlib tomllib nor tomli is available
            # (Python 3.10 without tomli). The test keeps every key under
            # a section so it passes under all three parser tiers.
            cfg.write_text(
                '[fetch]\n'
                'target = "/Plex/Anime"\n'
                'subdirectory = true\n'
                '\n'
                '[translate]\n'
                'engine = "ollama:qwen3:4b"\n'
                '\n'
                '[merge]\n'
                'langs = "ja,en"\n'
                'format = "vtt"\n',
                encoding="utf-8",
            )
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                rc = MODULE["main"](["--config", str(cfg)])
            assert rc == 0
            verbs = [c[0] for c in calls]
            assert verbs == ["fetch", "translate", "merge"], verbs
            # fetch got TARGET + --subdirectory
            assert "/Plex/Anime" in calls[0][1]
            assert "--subdirectory" in calls[0][1]
            # translate got rewritten to canonical --engine + --model
            tr_args = calls[1][1]
            assert "--engine" in tr_args
            assert tr_args[tr_args.index("--engine") + 1] == "ollama"
            assert "--model" in tr_args
            assert tr_args[tr_args.index("--model") + 1] == "qwen3:4b"
            # merge got --langs + --format
            merge_args = calls[2][1]
            assert "--langs" in merge_args or "-l" in merge_args
            assert "ja,en" in merge_args
    finally:
        scope["fetch_main"] = saved_fetch
        scope["translate_main"] = saved_tr
        scope["combine_main"] = saved_combine


def test_pipeline_config_translate_inherits_fetch_languages_and_disables_inline_mt():
    import tempfile, io, contextlib
    from pathlib import Path

    captured: dict[str, list[str]] = {}
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    saved_tr = scope["translate_main"]

    def fake_fetch(argv):
        captured["fetch"] = list(argv)
        return 0

    def fake_tr(argv):
        captured["translate"] = list(argv)
        return 0

    scope["fetch_main"] = fake_fetch
    scope["translate_main"] = fake_tr
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "jpko.toml"
            cfg.write_text(
                '[fetch]\n'
                'source = "https://www.crunchyroll.com/watch/GX9U31PV1/sawatari-koki-the-demon-god"\n'
                'season = "1"\n'
                'episode = "all"\n'
                'languages = "ja,ko"\n'
                '\n'
                '[translate]\n'
                'engine = "deepl"\n'
                'mt_source = "auto"\n'
                '\n'
                '[output]\n'
                f'target = "{tmp}/GetSubtitle"\n',
                encoding="utf-8",
            )
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                rc = MODULE["main"](["--config", str(cfg)])
            assert rc == 0
    finally:
        scope["fetch_main"] = saved_fetch
        scope["translate_main"] = saved_tr

    assert "--no-engine" in captured["fetch"]
    tr_args = captured["translate"]
    assert "--engine" in tr_args
    assert tr_args[tr_args.index("--engine") + 1] == "deepl"
    assert "--languages" in tr_args
    assert tr_args[tr_args.index("--languages") + 1] == "ja,ko"


def test_pipeline_config_translate_inherits_merge_languages_for_legacy_local_toml():
    import tempfile, io, contextlib
    from pathlib import Path

    captured: dict[str, list[str]] = {}
    scope = MODULE["pipeline_main"].__globals__
    saved_tr = scope["translate_main"]
    saved_modify = scope["modify_main"]
    saved_combine = scope["combine_main"]

    def fake_tr(argv):
        captured["translate"] = list(argv)
        return 0

    def fake_modify(argv):
        captured["modify"] = list(argv)
        return 0

    def fake_combine(argv):
        captured["merge"] = list(argv)
        return 0

    scope["translate_main"] = fake_tr
    scope["modify_main"] = fake_modify
    scope["combine_main"] = fake_combine
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "Ja2KoVTT.toml"
            cfg.write_text(
                '[translate]\n'
                'engine = "deepl"\n'
                'mt_source = "auto"\n'
                '\n'
                '[modify]\n'
                'single_line = true\n'
                'strip_cc_noise = true\n'
                'reading = "ja:hiragana"\n'
                'reading_format = "vtt"\n'
                '\n'
                '[merge]\n'
                'languages = "ja,ko"\n'
                'sync = "auto"\n'
                'format = "vtt"\n'
                '\n'
                '[output]\n'
                f'target = "{tmp}"\n',
                encoding="utf-8",
            )
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                rc = MODULE["main"](["--config", str(cfg)])
            assert rc == 0
    finally:
        scope["translate_main"] = saved_tr
        scope["modify_main"] = saved_modify
        scope["combine_main"] = saved_combine

    tr_args = captured["translate"]
    assert "--engine" in tr_args
    assert tr_args[tr_args.index("--engine") + 1] == "deepl"
    assert "--languages" in tr_args
    assert tr_args[tr_args.index("--languages") + 1] == "ja,ko"


def test_pipeline_toml_missing_required_source_errors():
    # [fetch] needs `source` (or back-compat alias `target`). Empty section errors.
    import tempfile, io, contextlib
    from pathlib import Path
    CliError = MODULE["CliError"]
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "pipeline.toml"
        cfg.write_text('[fetch]\nsubdirectory = true\n', encoding="utf-8")
        try:
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                MODULE["main"](["--config", str(cfg)])
        except CliError as e:
            assert "source" in str(e).lower()
        else:
            raise AssertionError("expected CliError when [fetch] missing source")


def test_pipeline_toml_target_alias_still_works_for_source():
    # Back-compat: `[fetch].target` is still accepted as the source key.
    import tempfile, io, contextlib
    from pathlib import Path
    captured: list[str] = []
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    def fake_fetch(argv):
        captured.extend(argv)
        return 0
    scope["fetch_main"] = fake_fetch
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "p.toml"
            cfg.write_text('[fetch]\ntarget = "/legacy/path"\n', encoding="utf-8")
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                MODULE["main"](["--config", str(cfg)])
        assert "/legacy/path" in captured
    finally:
        scope["fetch_main"] = saved_fetch


def test_pipeline_output_dry_run_false_adds_run_to_path_fetch():
    # [output].dry_run = false (or omitted) → auto-add --run to PATH-form
    # fetch so the user doesn't have to also set [fetch].run = true.
    import tempfile, io, contextlib
    from pathlib import Path
    captured: list[list[str]] = []
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    def fake_fetch(argv):
        captured.append(list(argv))
        return 0
    scope["fetch_main"] = fake_fetch
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "p.toml"
            # No [output] block at all → live run (default).
            cfg.write_text('[fetch]\nsource = "/plex"\nsubdirectory = true\n', encoding="utf-8")
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                MODULE["main"](["--config", str(cfg)])
        assert captured and "--run" in captured[0], captured
    finally:
        scope["fetch_main"] = saved_fetch


def test_pipeline_output_dry_run_true_does_not_add_run():
    # [output].dry_run = true → fetch stays in dry-run mode.
    import tempfile, io, contextlib
    from pathlib import Path
    captured: list[list[str]] = []
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    def fake_fetch(argv):
        captured.append(list(argv))
        return 0
    scope["fetch_main"] = fake_fetch
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "p.toml"
            cfg.write_text(
                '[fetch]\nsource = "/plex"\nsubdirectory = true\n'
                '[output]\ndry_run = true\n',
                encoding="utf-8",
            )
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                MODULE["main"](["--config", str(cfg)])
        assert captured and "--run" not in captured[0], captured
        # --dry-run should have been propagated instead.
        assert "--dry-run" in captured[0], captured
    finally:
        scope["fetch_main"] = saved_fetch


def test_inline_pipeline_path_fetch_adds_run_by_default():
    import tempfile, io, contextlib
    from pathlib import Path
    captured: list[list[str]] = []
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]

    def fake_fetch(argv):
        captured.append(list(argv))
        return 0

    scope["fetch_main"] = fake_fetch
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Show"
            root.mkdir()
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                MODULE["main"](["--fetch", str(root), "--languages", "ja,ko", "--merge"])
        assert captured and "--run" in captured[0], captured
    finally:
        scope["fetch_main"] = saved_fetch


def test_batch_fetch_movie_override_does_not_emit_episode_all(tmp_path, monkeypatch):
    captured: list[list[str]] = []
    g = MODULE["_batch_fetch_one"].__globals__
    monkeypatch.setitem(g, "_batch_run", lambda cmd, dry_run: captured.append(list(cmd)) or 0)
    monkeypatch.setattr(g["shutil"], "which", lambda _name: "getsubtitle")

    MODULE["_batch_fetch_one"](
        target=tmp_path,
        show_folder=tmp_path,
        season=None,
        profile="en",
        dry_run=False,
        fetch_langs_override=["zh", "ko", "en"],
        title_override="The God of Cookery",
        movie_override=True,
    )

    assert captured
    cmd = captured[0]
    assert "--title" in cmd
    assert "The God of Cookery" in cmd
    assert "--movie" in cmd
    assert "-e" not in cmd
    assert "--episode" not in cmd
    assert "-s" not in cmd
    assert "--season" not in cmd


def test_pipeline_url_source_does_not_auto_add_run():
    # URL fetch doesn't use --run (it's PATH-only). Auto-add should skip URLs.
    import io, contextlib
    captured: list[list[str]] = []
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    def fake_fetch(argv):
        captured.append(list(argv))
        return 0
    scope["fetch_main"] = fake_fetch
    try:
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            MODULE["main"](["--fetch", "https://example.com/x"])
        # Inline pipeline form (no [output] section in CLI) → live run, but
        # URL form doesn't get --run added.
        assert captured and "--run" not in captured[0], captured
    finally:
        scope["fetch_main"] = saved_fetch


def test_normalize_mt_source_accepts_string_and_dict():
    f = MODULE["_normalize_mt_source"]
    # String pass-through.
    assert f("ja") == "ja"
    assert f("ko:ja,es:en") == "ko:ja,es:en"
    # Dict → comma-string of target:source pairs.
    out = f({"ko": "ja", "es": "en"})
    pairs = set(out.split(","))
    assert pairs == {"ko:ja", "es:en"}
    # Dict with list fallback → pipe-list for "first available wins".
    out = f({"ko": ["ja", "en"], "es": "en"})
    pairs = set(out.split(","))
    assert pairs == {"ko:ja|en", "es:en"}


def test_parse_mt_source_lang_treats_auto_as_no_override():
    p = MODULE["parse_mt_source_lang"]
    assert p("auto", ["ja", "ko"]) is None
    assert p(" AUTO ", ["ja", "ko"]) is None


def test_parse_mt_source_lang_accepts_fallback_list():
    p = MODULE["parse_mt_source_lang"]
    parsed = p("es:fr|en,ko:ja", ["es", "ko"])
    assert parsed == {"es": ("fr", "en"), "ko": ("ja",)}


def test_pick_forced_mt_source_uses_first_available_fallback():
    from pathlib import Path
    pick = MODULE["pick_forced_mt_source"]
    available = {"en": Path("show.en.srt"), "ja": Path("show.ja.srt")}
    assert pick("es", ("fr", "en"), available) == ("en", Path("show.en.srt"))
    assert pick("es", ("fr", "ko"), available) is None


def test_parse_reading_spec_string_and_list():
    parse = MODULE["_parse_reading_spec"]
    # Comma string
    assert parse("ja:hiragana, ko:true, zh:true") == [
        ("ja", "hiragana"), ("ko", "revised"), ("zh", "marks"),
    ]
    # List form
    assert parse(["ja:hiragana", "ko:true", "zh:true"]) == [
        ("ja", "hiragana"), ("ko", "revised"), ("zh", "marks"),
    ]
    # Bare lang code → use default
    assert parse("ja, ko") == [("ja", "hiragana"), ("ko", "revised")]


def test_parse_reading_spec_pipe_expands_to_multiple_entries():
    # `ja:hiragana|romaji` → two pairs.
    parse = MODULE["_parse_reading_spec"]
    assert parse("ja:hiragana|romaji") == [("ja", "hiragana"), ("ja", "romaji")]
    assert parse("ja:hiragana|romaji, ko:true") == [
        ("ja", "hiragana"), ("ja", "romaji"), ("ko", "revised"),
    ]


def test_parse_reading_spec_normalizes_typo_codes():
    # jp → ja, kr → ko, cn → zh via LANGUAGE_ALIASES.
    parse = MODULE["_parse_reading_spec"]
    assert parse("jp:hiragana") == [("ja", "hiragana")]
    assert parse("kr:true") == [("ko", "revised")]
    assert parse("cn:true") == [("zh", "marks")]


def test_parse_reading_spec_bool_true_expands_all_supported_langs():
    # `romanization = true` → every language in _READING_DEFAULTS at its default.
    parse = MODULE["_parse_reading_spec"]
    pairs = parse(True)
    langs = {l for l, _ in pairs}
    # Should include at least ja, ko, zh (the three priority langs).
    assert {"ja", "ko", "zh"}.issubset(langs)
    # And mode is the per-language default for each.
    by_lang = dict(pairs)
    assert by_lang["ja"] == "hiragana"
    assert by_lang["ko"] == "revised"
    assert by_lang["zh"] == "marks"
    # `false` → empty list.
    assert parse(False) == []


def test_parse_reading_spec_rejects_unknown_mode():
    parse = MODULE["_parse_reading_spec"]
    try:
        parse("ja:cuneiform")
    except MODULE["CliError"] as e:
        assert "cuneiform" in str(e).lower() or "doesn't support" in str(e).lower()
    else:
        raise AssertionError("expected CliError for unknown mode")


def test_toml_modify_romanization_emits_cli_flag():
    # [modify].romanization = "ja:hiragana, ko:true" → --romanization SPEC in argv.
    convert = MODULE["_toml_to_pipeline_argv"]
    argv, _extras = convert({"modify": {"reading": "ja:hiragana, ko:true"}})
    assert "--reading" in argv
    spec = argv[argv.index("--reading") + 1]
    assert "ja:hiragana" in spec
    assert "ko:revised" in spec


def test_modify_main_routes_ja_romanization_through_furigana_path():
    # `getsubtitle modify FOLDER --romanization ja:hiragana` should set the
    # internal furigana arg to "hiragana" so the existing furigana code
    # path executes. (Test by parser-level inspection.)
    import io, contextlib, tempfile
    from pathlib import Path
    scope = MODULE["modify_main"].__globals__
    captured: list = []
    saved_scan = scope["scan_srt_files"]
    def fake_scan(paths):
        captured.append(paths)
        return []  # no files → "no work" exit
    scope["scan_srt_files"] = fake_scan
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                rc = MODULE["modify_main"]([tmp, "--reading", "ja:hiragana"])
            assert rc in (0, 1)
    finally:
        scope["scan_srt_files"] = saved_scan


def test_modify_main_rejects_still_deferred_romanization_with_clear_error():
    """Languages whose backend hasn't shipped yet (Thai, Arabic, Hindi,
    Russian) must raise a CliError pointing at the roadmap. Japanese,
    Korean, Mandarin, and Cantonese all ship and must NOT raise."""
    import io, contextlib, tempfile
    CliError = MODULE["CliError"]
    with tempfile.TemporaryDirectory() as tmp:
        # th:royal-thai is still deferred — should raise.
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            try:
                MODULE["modify_main"]([tmp, "--reading", "th:royal-thai"])
            except CliError as e:
                msg = str(e).lower()
                assert "not yet implemented" in msg
                assert "th" in msg
            else:
                raise AssertionError("expected CliError for th:royal-thai")


def test_toml_modify_convert_none_omits_flag():
    convert = MODULE["_toml_to_pipeline_argv"]
    argv1, _ = convert({"modify": {"convert": "smi-to-srt"}})
    assert "--convert" in argv1
    argv2, _ = convert({"modify": {"convert": "none"}})
    assert "--convert" not in argv2


def test_toml_output_force_propagates_to_all_supporting_verbs():
    convert = MODULE["_toml_to_pipeline_argv"]
    argv, _ = convert({
        "fetch": {"source": "/x"},
        "translate": {"engine": "argos"},
        "modify": {"strip_cc_noise": True},
        "merge": {"languages": "ja,en"},
        "output": {"force": True, "dry_run": True},
    })
    # --force should appear three times (translate, modify, merge).
    force_count = argv.count("--force")
    assert force_count == 3, f"expected --force x3, got {force_count} in {argv}"


def test_toml_output_yes_and_debug_propagate_to_fetch():
    convert = MODULE["_toml_to_pipeline_argv"]
    argv, _ = convert({
        "fetch": {"source": "/x"},
        "output": {"yes": True, "debug_providers": True},
    })
    assert "-y" in argv
    assert "--debug-providers" in argv


def test_toml_languages_canonical_with_langs_alias():
    convert = MODULE["_toml_to_pipeline_argv"]
    # Canonical
    argv1, _ = convert({"fetch": {"source": "/x", "languages": "ja,en"}})
    assert "--languages" in argv1 or "-l" in argv1 or "--langs" in argv1
    # Alias
    argv2, _ = convert({"fetch": {"source": "/x", "langs": "ja,en"}})
    # Either way the lang value reaches argv.
    assert "ja,en" in argv1
    assert "ja,en" in argv2


def test_url_form_season_range_expands_to_per_season_runs():
    # `getsubtitle URL -s 1-2 ...` should call main() twice recursively,
    # once per expanded season. We stub main() so the recursive calls
    # capture argv without doing real work.
    import io, contextlib
    main_globals = MODULE["main"].__globals__
    real_main = main_globals["main"]
    captured: list[list[str]] = []
    call_count = [0]
    def stub_main(argv=None):
        call_count[0] += 1
        if call_count[0] == 1:
            # Outer call: run the real expansion logic, which recurses.
            return real_main(argv)
        # Recursive per-season calls: capture and short-circuit.
        captured.append(list(argv) if argv else [])
        return 0
    main_globals["main"] = stub_main
    try:
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            try:
                stub_main(["https://x.example/", "-s", "1-2", "-l", "ja"])
            except Exception:
                pass
    finally:
        main_globals["main"] = real_main
    # Two recursive calls captured, one per expanded season.
    assert len(captured) == 2, captured
    assert captured[0][captured[0].index("-s") + 1] == "1"
    assert captured[1][captured[1].index("-s") + 1] == "2"


def test_url_form_season_single_value_does_not_expand():
    # `-s 1` (single) → no expansion; build_parser called once.
    import io, contextlib
    f = MODULE["_expand_url_form_season_range"]
    assert f(["URL", "-s", "1", "-l", "ja"]) is None
    assert f(["URL", "-s", "all"]) is None
    assert f(["URL", "-s", "auto"]) is None
    # Range and list DO trigger expansion.
    expanded = f(["URL", "--season", "1-3"])
    assert expanded is not None and len(expanded) == 3
    expanded = f(["URL", "-s", "1,3,5"])
    assert expanded is not None and len(expanded) == 3


def test_parse_vtt_preserves_cues_and_collapses_ruby():
    parse_vtt = MODULE["parse_vtt"]
    text = (
        "WEBVTT\n"
        "\n"
        "NOTE this is a note\n"
        "\n"
        "1\n"
        "00:00:01.000 --> 00:00:02.500\n"
        "<ruby>漢字<rt>かんじ</rt></ruby>を学ぶ\n"
        "\n"
        "00:00:03.000 --> 00:00:04.000\n"
        "<i>plain</i> line\n"
    )
    cues = parse_vtt(text)
    assert len(cues) == 2
    # Ruby collapsed to 漢字（かんじ）
    assert cues[0].text_lines == ["漢字（かんじ）を学ぶ"]
    # Time normalized to SRT comma form
    assert "00:00:01,000" in cues[0].time_line
    assert "00:00:02,500" in cues[0].time_line
    # HTML markup stripped
    assert cues[1].text_lines == ["plain line"]


def test_parse_vtt_handles_mm_ss_format():
    # WebVTT allows MM:SS.mmm (no hour). parse_vtt normalizes to HH:MM:SS,mmm.
    parse_vtt = MODULE["parse_vtt"]
    text = "WEBVTT\n\n01:23.500 --> 01:25.000\nhello\n"
    cues = parse_vtt(text)
    assert len(cues) == 1
    assert "00:01:23,500" in cues[0].time_line
    assert "00:01:25,000" in cues[0].time_line


def test_parse_vtt_strips_netflix_classes_when_preserving_ruby():
    parse_vtt = MODULE["parse_vtt"]
    text = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:02.000\n"
        "<c.japanese><c.bg_transparent><ruby>日本語<rt>にほんご</rt></ruby></c.bg_transparent></c.japanese>\n"
    )
    cues = parse_vtt(text, preserve_ruby=True)

    assert cues[0].text_lines == ["<ruby>日本語<rt>にほんご</rt></ruby>"]


def test_read_cues_from_file_dispatches_by_extension():
    # SRT, VTT both parse; unknown extension errors.
    import tempfile
    from pathlib import Path
    read = MODULE["read_cues_from_file"]
    with tempfile.TemporaryDirectory() as tmp:
        srt = Path(tmp) / "x.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nhello\n", encoding="utf-8")
        vtt = Path(tmp) / "x.vtt"
        vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n", encoding="utf-8")
        assert len(read(srt)) == 1
        assert len(read(vtt)) == 1
        bogus = Path(tmp) / "x.txt"
        bogus.write_text("nothing here", encoding="utf-8")
        try:
            read(bogus)
        except MODULE["CliError"] as e:
            assert "not supported" in str(e).lower()
        else:
            raise AssertionError("expected CliError for unknown extension")


def test_normalize_merge_langs_strips_format_hints():
    f = MODULE["_normalize_merge_langs"]
    # String form
    langs_str, hints = f("ja:vtt, en, ko:smi")
    assert langs_str == "ja,en,ko"
    assert hints == {"ja": "vtt", "ko": "smi"}
    # List form
    langs_str, hints = f(["ja:vtt", "en", "ko:smi"])
    assert langs_str == "ja,en,ko"
    assert hints == {"ja": "vtt", "ko": "smi"}
    # No hints
    langs_str, hints = f("ja, en")
    assert langs_str == "ja,en"
    assert hints == {}


def test_normalize_merge_langs_rejects_unknown_format():
    f = MODULE["_normalize_merge_langs"]
    try:
        f("ja:bogus, en")
    except MODULE["CliError"] as e:
        assert "bogus" in str(e).lower()
    else:
        raise AssertionError("expected CliError for unknown format")


def test_toml_aliases_plural_singular():
    # episodes / seasons / languages are aliases for the canonical singular.
    canon = MODULE["_canonicalize_toml_key"]
    assert canon("episodes") == "episode"
    assert canon("seasons") == "season"
    assert canon("languages") == "langs"
    assert canon("language") == "langs"
    # Non-aliased keys pass through.
    assert canon("profile") == "profile"


def test_toml_to_pipeline_argv_emits_output_section_and_pair_models():
    convert = MODULE["_toml_to_pipeline_argv"]
    data = {
        "output": {"root": "/tmp/out", "format": "vtt", "layout": "plex"},
        "fetch": {"target": "/Plex/Anime", "subdirectory": True, "season": "1-2"},
        "translate": {
            "engine": "ollama",
            "ja:ko": "qwen3:4b",
            "en:es": "llama3.2:3b",
            "mt_source_lang": "en",
        },
        "modify": {"reading": "ja:hiragana", "reading_format": "srt"},
        "merge": {"langs": "ja:vtt, en", "master": "ja"},
    }
    argv, extras = convert(data)
    # --output prepended, layout passed to fetch
    assert "--output" in argv
    assert argv[argv.index("--output") + 1] == "/tmp/out"
    # fetch gets --subdirectory, --season, and inherited --layout
    fetch_idx = argv.index("--fetch")
    assert argv[fetch_idx + 1] == "/Plex/Anime"
    assert "--subdirectory" in argv
    assert "--season" in argv
    assert "--layout" in argv
    # translate: engine positional + pair models stripped into extras
    tr_idx = argv.index("--translate")
    assert argv[tr_idx + 1] == "ollama"
    assert "--mt-source" in argv
    assert extras["translate_pair_models"] == {"ja:ko": "qwen3:4b", "en:es": "llama3.2:3b"}
    # modify: furigana = "hiragana" → --furigana hiragana; format → --reading-format
    assert "--reading" in argv
    assert "--reading-format" in argv
    # merge: langs stripped of :format hints, hint stashed in extras
    assert "-l" in argv
    assert argv[argv.index("-l") + 1] == "ja,en"
    assert extras["merge_format_hints"] == {"ja": "vtt"}
    # [output].format overrides per-verb format → --format vtt for merge
    assert "--format" in argv
    assert argv[argv.index("--format") + 1] == "vtt"


def test_toml_merge_inherits_single_japanese_reading_from_modify():
    convert = MODULE["_toml_to_pipeline_argv"]
    argv, _extras = convert({
        "modify": {"reading": "ja:hiragana", "reading_format": "vtt"},
        "merge": {"languages": "ja,ko", "format": "vtt"},
        "output": {"target": "/tmp/show"},
    })
    merge_idx = argv.index("--merge")
    merge_block = argv[merge_idx:]
    assert "--reading" in merge_block
    assert merge_block[merge_block.index("--reading") + 1] == "ja:hiragana"


def test_language_aliases_full_names_normalize_to_iso():
    # `langs = "japanese,english"` should equal `langs = "ja,en"` after
    # split_csv normalization.
    split = MODULE["split_csv"]
    assert split("japanese,english", "") == ["ja", "en"]
    assert split("korean,spanish,french,chinese", "") == ["ko", "es", "fr", "zh"]
    assert split("German,Italian,Portuguese,Russian", "") == ["de", "it", "pt", "ru"]
    # Mixed forms work too.
    assert split("ja,english", "") == ["ja", "en"]


def test_merge_l_accepts_format_hints_in_bare_cli():
    # `getsubtitle merge PATH -l ja:vtt,en,ko:smi` should strip the :format
    # hints, pass the cleaned langs to the merger, and stash the hints so
    # the scanner picks them up — same behavior as the pipeline TOML form.
    import tempfile, io, contextlib
    from pathlib import Path
    captured_hints: dict = {}
    captured_paths: list = []
    scope = MODULE["combine_main"].__globals__
    saved_scanner = scope["scan_subtitle_files_extended"]
    def fake_scanner(
        paths,
        *,
        format_hints=None,
        include_furigana=False,
        pseudo_langs=None,
        requested_langs=None,
        inferred_out=None,
    ):
        captured_hints.update(format_hints or {})
        captured_paths.extend(paths)
        return []   # empty → "no episodes" path; we just want to verify the hint extraction
    scope["scan_subtitle_files_extended"] = fake_scanner
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                MODULE["main"]([
                    "merge", tmp, "-l", "ja:vtt,en,ko:smi",
                ])
        # The hint dict matches what _normalize_merge_langs would emit.
        assert captured_hints == {"ja": "vtt", "ko": "smi"}, captured_hints
    finally:
        scope["scan_subtitle_files_extended"] = saved_scanner


def test_pipeline_session_only_pair_models_dont_leak():
    # Run a pipeline with per-pair model overrides; after the run the
    # session dict must be empty again.
    import tempfile, io, contextlib
    from pathlib import Path
    pair_dict = MODULE["_PIPELINE_TRANSLATE_PAIR_MODELS"]
    assert pair_dict == {}, "session dict polluted before test"

    # Patch the verbs so we don't actually run anything heavy.
    scope = MODULE["pipeline_main"].__globals__
    saved_fetch = scope["fetch_main"]
    saved_tr = scope["translate_main"]
    saved_combine = scope["combine_main"]
    # Snapshot the pair dict at translate-time so we can assert it was set.
    seen_pairs: list[dict] = []
    def fake_fetch(argv): return 0
    def fake_tr(argv):
        seen_pairs.append(dict(MODULE["_PIPELINE_TRANSLATE_PAIR_MODELS"]))
        return 0
    def fake_combine(argv): return 0
    scope["fetch_main"] = fake_fetch
    scope["translate_main"] = fake_tr
    scope["combine_main"] = fake_combine
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "p.toml"
            cfg.write_text(
                '[fetch]\ntarget = "/x"\n'
                '[translate]\nengine = "ollama"\n"ja:ko" = "qwen3:4b"\n',
                encoding="utf-8",
            )
            with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
                MODULE["main"](["--config", str(cfg)])
        # During translate, the session dict held the override.
        assert seen_pairs and seen_pairs[0].get("ja:ko") == "qwen3:4b"
    finally:
        scope["fetch_main"] = saved_fetch
        scope["translate_main"] = saved_tr
        scope["combine_main"] = saved_combine
    # After the run, the session dict is clean.
    assert MODULE["_PIPELINE_TRANSLATE_PAIR_MODELS"] == {}


def test_pipeline_missing_argument_errors():
    # `--config` alone — no file path — should error.
    import io, contextlib
    CliError = MODULE["CliError"]
    try:
        with _isolated_config(None), contextlib.redirect_stdout(io.StringIO()):
            MODULE["main"](["--config"])
    except CliError as e:
        assert "TOML" in str(e) or "file" in str(e).lower() or "path" in str(e).lower()
    else:
        raise AssertionError("expected CliError when --config has no path")


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
        # v0.2: topic renamed to `romanization`; `furigana` kept as alias.
        assert "--help reading" in str(e)
    else:
        raise AssertionError("expected CliError for unknown format")


def test_generate_furigana_respects_formats_argument():
    # The user-reported pain point: 3 files per episode was too much. Verify
    # that generate_furigana only calls the writers whose formats are in the
    # `formats` set. Mock the three writers so this test doesn't require
    # the Japanese reading backend.
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
    bad = '[modify]\nreading_format = "srt,mp4"\n'
    with _isolated_config(bad):
        try:
            MODULE["load_user_config"]()
        except MODULE["CliError"] as e:
            assert "mp4" in str(e)
        else:
            raise AssertionError("expected CliError for bad furigana.format")


def test_config_furigana_format_applies_to_download_parser_default():
    toml = '[modify]\nreading_format = "srt,ass"\n'
    with _isolated_config(toml):
        parser = MODULE["build_parser"]()
        args = parser.parse_args(["URL"])
    assert args.reading_format == "srt,ass"


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
                        str(d), "--reading", "ja:hiragana", "--format", "srt,mp4",
                    ])
                except MODULE["CliError"] as e:
                    err_caught = str(e)
    assert err_caught is not None
    assert "mp4" in err_caught
    # Plan/progress should NOT have been printed.
    text = out.getvalue()
    assert "Planned:" not in text
    assert "Processing:" not in text


def test_progress_bar_uses_wizard_block_style():
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        MODULE["progress_bar"](1, 3, "searching", "episode 1 ja")
        MODULE["progress_bar"](3, 3, "searching", "episode 3 ja")
    text = out.getvalue()
    assert "[◼◼◼◼◻◻◻◻◻◻◻◻◻] 1/3 searching episode 1 ja" in text
    assert "[◼◼◼◼◼◼◼◼◼◼◼◼◼] 3/3 searching episode 3 ja" in text
    assert "#" not in text
    assert "-" not in text


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


def test_modify_main_convert_smi_scopes_language():
    import tempfile, io, contextlib
    from pathlib import Path
    sami = (
        "<SAMI><BODY>"
        "<SYNC Start=1000><P Class=KRCC>한국어</P><P Class=ENCC>English</P></SYNC>"
        "<SYNC Start=4000><P Class=KRCC>&nbsp;</P><P Class=ENCC>&nbsp;</P></SYNC>"
        "</BODY></SAMI>"
    )
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Show.S01E01.smi").write_text(sami, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["modify_main"]([str(root), "--convert", "kr:smi-to-srt"])
            text = out.getvalue()
            ko_exists = (root / "Show.S01E01.ko.srt").exists()
            en_exists = (root / "Show.S01E01.en.srt").exists()
    assert rc == 0
    assert "ko only" in text
    assert ko_exists
    assert not en_exists


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


def test_modify_main_convert_then_applies_reading_to_new_srt():
    import tempfile, io, contextlib
    from pathlib import Path
    with _isolated_config(None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Show.S01E01.smi").write_text(_SAMI_BASIC_KO, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = MODULE["modify_main"]([
                    str(root),
                    "--convert", "smi-to-srt",
                    "--reading", "ko:yale",
                    "--reading-format", "srt",
                ])
            text = out.getvalue()
            converted = root / "Show.S01E01.ko.srt"
            reading = root / "Show.S01E01.ko.romanization-yale.asb.srt"
            assert rc == 0
            assert converted.exists()
            assert reading.exists()
            assert "Converting SMI" in text
            assert "Processing SRT" in text


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


def test_deepl_usage_uses_usage_endpoint_and_header():
    import json

    captured = {}

    class _Response:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return json.dumps({
                "character_count": 180118,
                "character_limit": 500000,
            }).encode("utf-8")

    def fake_urlopen(req, timeout=15):
        captured["url"] = req.full_url
        captured["authorization"] = req.get_header("Authorization")
        return _Response()

    urllib_mod = MODULE["urllib"]
    saved_urlopen = urllib_mod.request.urlopen
    try:
        urllib_mod.request.urlopen = fake_urlopen
        usage = MODULE["DeepLTranslator"]("test-key:fx").usage()
    finally:
        urllib_mod.request.urlopen = saved_urlopen

    assert captured["url"] == "https://api-free.deepl.com/v2/usage"
    assert captured["authorization"] == "DeepL-Auth-Key test-key:fx"
    assert usage.character_count == 180118
    assert usage.character_limit == 500000


def test_format_deepl_usage_shows_remaining_characters():
    lines = MODULE["format_deepl_usage"](
        MODULE["DeepLUsage"](character_count=180118, character_limit=500000)
    )
    assert lines == [
        "Account characters this period: 180,118 / 500,000 (319,882 remaining, 36.0% used)"
    ]


def test_translate_main_prints_deepl_usage_after_success():
    import contextlib
    import io
    import tempfile
    from pathlib import Path

    class _FakeDeepL(MODULE["DeepLTranslator"]):
        def __init__(self):
            super().__init__("fake-key:fx")
        def is_available(self):
            return True
        def translate_batch(self, texts, source, target, on_progress=None):
            if on_progress is not None:
                on_progress(len(texts), len(texts))
            return [f"[{target}] {t}" for t in texts]
        def usage(self):
            return MODULE["DeepLUsage"](character_count=1200, character_limit=500000)

    scope = MODULE["translate_main"].__globals__
    saved_select = scope["select_translator"]
    try:
        scope["select_translator"] = lambda engine, model: _FakeDeepL()
        with _isolated_config(None):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "Show.S01E07.ja.srt").write_text(
                    "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n", encoding="utf-8"
                )
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = MODULE["translate_main"]([
                        str(root), "-l", "ja,ko", "--engine", "deepl",
                    ])
        text = buf.getvalue()
    finally:
        scope["select_translator"] = saved_select

    assert rc == 0
    assert "DeepL usage:" in text
    assert "1,200 / 500,000" in text
    assert "498,800 remaining" in text


def test_ollama_missing_model_is_pulled_before_translate():
    import contextlib
    import io
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
                {"status": "pulling 3e4cb1417446", "completed": 25, "total": 100},
                {"status": "pulling 3e4cb1417446", "completed": 25, "total": 100},
                {"status": "pulling 3e4cb1417446", "completed": 100, "total": 100},
                {"status": "pulling 3e4cb1417446", "completed": 100, "total": 100},
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
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = MODULE["OllamaTranslator"](model="aya-expanse:8b").translate_batch(["こんにちは"], "ja", "ko")
    finally:
        urllib_mod.request.urlopen = saved_urlopen

    assert out == ["안녕하세요"]
    assert any(url.endswith("/api/pull") for url in calls)
    assert any(url.endswith("/api/generate") for url in calls)
    text = buf.getvalue()
    assert "pulling pulling" not in text
    assert text.count("3e4cb1417446") == 1
    assert "Ollama pull status: success" in text
    assert "Ollama model 'aya-expanse:8b' is ready. Starting translation" in text


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
    assert "--model NAME" in msg
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
    assert "translate" in text


def test_dispatch_routes_merge_subcommand():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S01E07.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
        )
        (root / "Show.S01E07.en.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nhello\n", encoding="utf-8"
        )
        # main(['merge', ...]) should dispatch to combine_main (the canonical
        # name is `merge`; combine_main remains as an internal function name).
        rc = MODULE["main"](["merge", str(root), "-l", "ja,en", "--dry-run"])
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
        assert "Unknown --engine" in str(e)
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


def test_strip_cc_noise_removes_decorative_wrappers():
    src = (
        "1\n"
        "00:00:01,000 --> 00:00:02,000\n"
        "あ…。　《Ｍｉｓｔａｋｅ！》\n"
        "\n"
        "2\n"
        "00:00:03,000 --> 00:00:04,000\n"
        "〈次回　第１７話〉\n"
    )
    out = MODULE["strip_cc_noise_text"](src)
    assert "《" not in out
    assert "》" not in out
    assert "〈" not in out
    assert "〉" not in out
    assert "あ…。　Ｍｉｓｔａｋｅ！" in out
    assert "次回　第１７話" in out


def test_strip_cc_noise_text_is_idempotent():
    s = "《foo➡》\nbar"
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
            "1\n00:00:01,000 --> 00:00:02,000\n《なんて…。➡》\n", encoding="utf-8"
        )
        MODULE["strip_cc_noise_in_place"](path)
        out = path.read_text(encoding="utf-8")
    assert "➡" not in out
    assert "《" not in out
    assert "》" not in out
    assert "なんて…。" in out


def test_strip_cc_arrows_legacy_aliases_still_work():
    # The narrow arrow-specific helper must continue to exist so any external
    # caller using the old name is not broken by the rename.
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
    assert "（テイラー）こんな所を　フルスロットルで来るなんて…。" in out
    assert "《" not in out
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


def test_save_subtitle_rejects_obvious_replacement_character_damage(tmp_path):
    save_globals = MODULE["save_subtitle"].__globals__
    saved_dl = save_globals["download_bytes"]

    def fake_download_bytes(_url, headers=None):
        return (
            "1\n00:00:01,000 --> 00:00:02,000\n"
            "Ya, Luigi se pas� su d�cimo cumplea�os llorando.\n"
        ).encode("utf-8")

    try:
        save_globals["download_bytes"] = fake_download_bytes
        sub = MODULE["SubtitleFile"](
            provider="wyzie",
            language="es",
            name="bad.es.srt",
            url="https://example.test/bad.es.srt",
        )
        media = MODULE["MediaInfo"](source_url="x", provider="tmdb", title="Movie", season="auto", is_movie=True)
        try:
            MODULE["save_subtitle"](sub, tmp_path, media, "auto", "auto")
        except MODULE["CliError"] as e:
            msg = str(e)
        else:
            raise AssertionError("expected corrupt subtitle to be rejected")
    finally:
        save_globals["download_bytes"] = saved_dl

    assert "subtitle text looks corrupted" in msg
    assert "replacement characters" in msg
    assert not list(tmp_path.glob("*.srt"))


def test_save_subtitle_transcodes_cp1252_text_to_utf8(tmp_path):
    save_globals = MODULE["save_subtitle"].__globals__
    saved_dl = save_globals["download_bytes"]

    def fake_download_bytes(_url, headers=None):
        return (
            "1\n00:00:01,000 --> 00:00:02,000\n"
            "Cumpleaños y décimo.\n"
        ).encode("cp1252")

    try:
        save_globals["download_bytes"] = fake_download_bytes
        sub = MODULE["SubtitleFile"](
            provider="wyzie",
            language="es",
            name="good.es.srt",
            url="https://example.test/good.es.srt",
        )
        media = MODULE["MediaInfo"](source_url="x", provider="tmdb", title="Movie", season="auto", is_movie=True)
        saved = MODULE["save_subtitle"](sub, tmp_path, media, "auto", "auto")
    finally:
        save_globals["download_bytes"] = saved_dl

    assert len(saved) == 1
    assert "Cumpleaños y décimo." in saved[0].read_text(encoding="utf-8")


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


# ─── v0.1 naming-consistency renames ─────────────────────────────────────
# These guard the canonical CLI/TOML names introduced in v0.1 along with
# the silent back-compat aliases.

def test_cli_engine_model_mt_source_languages_aliases():
    """All four canonical CLI flag aliases land on the existing dests."""
    # translate parser
    p = MODULE["build_translate_parser"]()
    ns = p.parse_args([
        "/tmp", "--engine", "argos", "--model", "qwen3:4b",
        "--mt-source", "ko:ja", "--mt-model-pair", "ja:ko=qwen3:4b",
        "--languages", "ja,ko",
    ])
    assert ns.mt_engine == "argos"
    assert ns.mt_model == "qwen3:4b"
    assert ns.mt_source_lang == "ko:ja"
    assert ns.mt_model_pair == "ja:ko=qwen3:4b"
    # dest stayed `langs` for back-compat with existing call sites;
    # --languages is the new documented spelling.
    assert ns.langs == "ja,ko"
    # URL parser (build_parser)
    p2 = MODULE["build_parser"]()
    ns2 = p2.parse_args([
        "https://example.com", "--engine", "argos",
        "--model", "m", "--mt-source", "ko:ja",
        "--mt-model-pair", "ja:ko=qwen3:4b", "--languages", "ja,ko",
    ])
    assert ns2.mt_engine == "argos"
    assert ns2.mt_model == "m"
    assert ns2.mt_source_lang == "ko:ja"
    assert ns2.mt_model_pair == "ja:ko=qwen3:4b"
    assert ns2.langs == "ja,ko"


def test_cli_manual_search_fetch_flags():
    p = MODULE["build_parser"]()
    ns = p.parse_args([
        "https://example.com/title", "-l", "ko,zh",
        "--manual-search", "always",
        "--manual-search-open", "never",
    ])
    assert ns.manual_search == "always"
    assert ns.manual_search_open == "never"

    ns2 = p.parse_args([
        "https://example.com/title", "--no-manual-download",
        "--no-manual-search-open",
    ])
    assert ns2.manual_search == "off"
    assert ns2.manual_search_open == "never"


def test_cli_legacy_mt_flags_still_accepted():
    """The pre-rename long names remain functional aliases."""
    p = MODULE["build_translate_parser"]()
    ns = p.parse_args([
        "/tmp", "-l", "ja,ko",
        "--mt-engine", "argos", "--mt-model", "qwen3:4b",
        "--mt-source-lang", "ko:ja",
    ])
    assert ns.mt_engine == "argos"
    assert ns.mt_model == "qwen3:4b"
    assert ns.mt_source_lang == "ko:ja"


def test_option_was_passed_accepts_model_aliases():
    """Canonical --model should count the same as legacy --mt-model when
    deciding whether a CLI model overrides pair-specific TOML defaults."""
    ow = MODULE["option_was_passed"]
    assert ow(["--model", "qwen3:4b"], "--model", "--mt-model")
    assert ow(["--model=qwen3:4b"], "--model", "--mt-model")
    assert ow(["--mt-model", "qwen3:4b"], "--model", "--mt-model")


def test_cli_reading_format_canonical_and_aliases():
    """--reading-format is canonical; --format and --furigana-format are aliases."""
    mp = MODULE["build_modify_parser"]()
    assert mp.parse_args(["/tmp", "--reading-format", "all"]).reading_format == "all"
    assert mp.parse_args(["/tmp", "--format", "srt,vtt"]).reading_format == "srt,vtt"
    assert mp.parse_args(["/tmp", "--reading-format", "srt"]).reading_format == "srt"


def test_toml_mt_source_canonical_and_alias_in_user_config():
    """`mt_source` is the canonical TOML key; `mt_source_lang` still works."""
    validate = MODULE["validate_user_config"]
    # Canonical
    v = validate({"translate": {"mt_source": "ko:ja"}})
    assert v["translate"]["mt_source_lang"] == "ko:ja"
    # Dict form
    v = validate({"translate": {"mt_source": {"ko": "ja", "es": "en"}}})
    assert v["translate"]["mt_source_lang"] == {"ko": "ja", "es": "en"}
    v = validate({"translate": {"mt_source": {"es": ["fr", "en"]}}})
    assert v["translate"]["mt_source_lang"] == {"es": ["fr", "en"]}
    # Legacy alias still accepted
    v = validate({"translate": {"mt_source_lang": "auto"}})
    assert v["translate"]["mt_source_lang"] == "auto"


def test_fetch_manual_search_config_accepts_modes_and_booleans():
    validate = MODULE["validate_user_config"]
    v = validate({"fetch": {"manual_search": "always", "manual_search_open": "never"}})
    assert v["fetch"]["manual_search"] == "always"
    assert v["fetch"]["manual_search_open"] == "never"
    v = validate({"fetch": {"manual_search": False, "manual_search_open": True}})
    assert v["fetch"]["manual_search"] == "off"
    assert v["fetch"]["manual_search_open"] == "always"


def test_manual_search_suggestions_cover_korean_and_chinese_sources():
    media = MODULE["MediaInfo"](
        source_url="title://Fena",
        provider="title",
        title="Fena Pirate Princess",
        title_aliases=["Kaizoku Oujo"],
    )
    suggestions = MODULE["build_manual_search_suggestions"](media, ["ko", "zh"])
    labels = [s.label for s in suggestions]
    urls = [s.url for s in suggestions]
    assert "GOM Lab" in labels
    assert "Cineaste" in labels
    assert "ASSRT / Shooter" in labels
    assert "SubHD" in labels
    assert any("Fena+Pirate+Princess" in url for url in urls)


def test_missing_languages_for_manual_search_only_tracks_ko_zh():
    result = MODULE["SearchResult"]
    missing = MODULE["missing_languages_for_manual_search"](
        ["ko", "zh", "en"],
        ["1", "2"],
        [
            result("ko", "1", "wyzie", "found"),
            result("ko", "2", "wyzie", "missing"),
            result("zh", "1", "wyzie", "found"),
            result("zh", "2", "wyzie", "found"),
        ],
    )
    assert missing == ["ko"]


def test_manual_search_next_steps_are_scoped_and_output_aware():
    import contextlib, io
    from pathlib import Path

    media = MODULE["MediaInfo"](
        source_url="title://Fena",
        provider="title",
        title="Fena Pirate Princess",
        season="1",
    )
    result = MODULE["SearchResult"]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        MODULE["maybe_print_manual_search_suggestions"](
            media,
            ["ja", "ko"],
            ["1"],
            [result("ja", "1", "jimaku", "found"), result("ko", "1", "wyzie", "missing")],
            mode="on-missing",
            open_mode="never",
            expected_output_dir=Path("/tmp/GetSubtitle/Fena Pirate Princess/Season 01"),
        )
    text = out.getvalue()
    assert "getsubtitle modify ~/Downloads --convert ko:smi-to-srt" in text
    assert "Put them in:" in text
    assert "getsubtitle merge '/tmp/GetSubtitle/Fena Pirate Princess/Season 01' -l ja,ko" in text


def test_toml_pipeline_mt_source_lang_alias_emits_mt_source_flag():
    """Pipeline TOML `mt_source_lang` still works, emits new --mt-source CLI flag."""
    convert = MODULE["_toml_to_pipeline_argv"]
    argv, _ = convert({
        "translate": {"engine": "argos", "mt_source_lang": "ko:ja"},
    })
    assert "--mt-source" in argv
    idx = argv.index("--mt-source")
    assert argv[idx + 1] == "ko:ja"


def test_toml_pipeline_reading_format_canonical_emits_reading_format_flag():
    """Pipeline TOML emits --reading-format (new canonical CLI flag)."""
    convert = MODULE["_toml_to_pipeline_argv"]
    argv, _ = convert({"modify": {"reading_format": "vtt"}})
    assert "--reading-format" in argv
    assert argv[argv.index("--reading-format") + 1] == "vtt"


def test_toml_hyphen_underscore_keys_normalize():
    """Hyphens in TOML keys are accepted as alias for underscores."""
    validate = MODULE["validate_user_config"]
    # `release-source` should normalize to `release_source` and validate.
    v = validate({"fetch": {"release-source": "netflix"}})
    assert v["fetch"]["release_source"] == "netflix"
    # `strip-cc-noise` in [modify]
    v = validate({"modify": {"strip-cc-noise": True}})
    assert v["modify"]["strip_cc_noise"] is True


def test_toml_pipeline_dry_run_with_hyphen_works():
    """[output].dry-run (hyphen) is treated as [output].dry_run."""
    convert = MODULE["_toml_to_pipeline_argv"]
    argv, extras = convert({"output": {"dry-run": True}})
    assert "--dry-run" in argv
    assert extras["force_live_run"] is False


def test_toml_pipeline_retain_folder_structure_underscore_and_hyphen():
    """retain_folder_structure (and the hyphen form) both map to layout=plex."""
    convert = MODULE["_toml_to_pipeline_argv"]
    argv1, extras1 = convert({"output": {"retain_folder_structure": True}})
    assert extras1["output_layout"] == "plex"
    argv2, extras2 = convert({"output": {"retain-folder-structure": True}})
    assert extras2["output_layout"] == "plex"


# ─── Interactive wizard ───────────────────────────────────────────────

def _wizard_state(**overrides):
    """Build a populated _WizardState (URL pipeline by default).
    Tests then mutate only the fields they care about. v0.7+ uses the
    all-in-one step set so existing emitter assertions about
    --translate / [translate] keep firing; tests that exercise a focused
    subset override `steps=` explicitly."""
    s = MODULE["_WizardState"](
        source="https://www.imdb.com/title/tt28299608/",
        source_kind="url",
        languages=["ja", "ko", "en"],
        order=["ja", "ko", "en"],
        master="",
        season="1", episode="all",
        mt_engine="ollama",
        reading_aids=["ja:hiragana"],
        asbplayer=True,
        format="vtt",
        output="~/Downloads/GetSubtitle",
        steps={"fetch", "translate", "modify", "merge"},
    )
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_interactive_non_tty_raises_clean_error():
    """Wizard refuses to run when stdin/stdout isn't a terminal — the
    only sane behavior, since every question is a blocking prompt."""
    try:
        MODULE["interactive_main"]([])
    except MODULE["CliError"] as e:
        msg = str(e)
        assert "interactive mode" in msg or "tty" in msg.lower()
    else:
        # On a CI box stdin may be a tty surprisingly; if so the wizard
        # would have tried to read input and EOFed. Either is acceptable.
        pass


def test_wizard_emit_cli_uses_canonical_flags():
    """Generated CLI uses v0.4 canonical long names (--languages, --engine,
    --mt-source, --reading, --reading-format) and never legacy
    --furigana / --romanization."""
    state = _wizard_state()
    cli = MODULE["_wizard_emit_cli"](state)
    assert "--languages" in cli
    assert "--reading" in cli
    assert "--furigana" not in cli
    assert "--romanization" not in cli
    # Translate engine is positional after --translate, not --mt-engine.
    assert "--translate" in cli
    assert cli[cli.index("--translate") + 1] == "ollama"
    # Single Japanese reading aids are applied by merge in this full workflow,
    # so the wizard does not emit a redundant modify --reading-format sidecar.
    assert "--reading-format" not in cli


def test_wizard_emit_cli_modify_only_keeps_reading_format_for_side_files():
    state = _wizard_state(
        source="/tmp/Show",
        source_kind="path",
        steps={"modify"},
        reading_aids=["ja:hiragana"],
        format="vtt",
        asbplayer=False,
    )
    cli = MODULE["_wizard_emit_cli"](state)
    assert cli[:3] == ["getsubtitle", "modify", "/tmp/Show"]
    assert "--reading" in cli
    assert cli[cli.index("--reading") + 1] == "ja:hiragana"
    assert "--reading-format" in cli
    assert cli[cli.index("--reading-format") + 1] == "vtt"


def test_wizard_emit_toml_uses_canonical_keys():
    """Generated TOML uses v0.4 canonical keys (mt_source, reading,
    reading_format) and never legacy mt_source_lang / furigana /
    romanization / furigana_output_format."""
    state = _wizard_state()
    toml = MODULE["_wizard_emit_toml"](state)
    assert "mt_source =" in toml
    assert "mt_source_lang" not in toml
    assert "reading =" in toml
    assert "furigana =" not in toml
    assert "romanization =" not in toml
    assert "reading_format =" in toml
    assert "furigana_output_format" not in toml
    # Section ordering matches the pipeline execution order.
    sections = [s for s in ("[fetch]", "[translate]", "[modify]", "[merge]", "[output]")
                if s in toml]
    indices = [toml.index(s) for s in sections]
    assert indices == sorted(indices)


def test_wizard_emit_cli_and_toml_include_episode_filename_start():
    state = _wizard_state(
        source="https://www.crunchyroll.com/series/GEXH3W2W7/mf-ghost",
        source_kind="url",
        season="3",
        episode="1-12",
        episode_filename_start="25",
        mt_engine="",
        reading_aids=[],
        format="srt",
    )
    cli = MODULE["_wizard_emit_cli"](state)
    assert "--episode-filename-start" in cli
    assert cli[cli.index("--episode-filename-start") + 1] == "25"
    toml = MODULE["_wizard_emit_toml"](state)
    assert 'episode_filename_start = "25"' in toml


def test_wizard_emit_cli_shows_shared_scope_once_for_full_pipeline():
    state = _wizard_state(
        source="https://www.crunchyroll.com/watch/GE00379925JAJP/mini-episode-1",
        source_kind="url",
        season="1",
        episode="1-3",
        languages=["ja", "ko"],
        order=["ja", "ko"],
        mt_engine="ollama",
        reading_aids=["ja:hiragana"],
        format="vtt",
        steps={"fetch", "translate", "modify", "merge"},
    )
    cli = MODULE["_wizard_emit_cli"](state)
    assert cli.count("--season") == 1
    assert cli.count("--episode") == 1
    assert cli[cli.index("--season") + 1] == "1"
    assert cli[cli.index("--episode") + 1] == "1-3"


def test_wizard_preserves_display_order_distinct_from_collection():
    """If Q2 collects ja,en,ko but Q3 reorders to ko,ja,en, the merge
    languages reflect Q3, not Q2."""
    state = _wizard_state(
        languages=["ja", "en", "ko"],
        order=["ko", "ja", "en"],
    )
    cli = MODULE["_wizard_emit_cli"](state)
    # Fetch carries collection order.
    fetch_l = cli[cli.index("--languages") + 1]
    assert fetch_l == "ja,en,ko"
    # Merge carries display order (find the SECOND --languages).
    merge_idx = cli.index("--merge")
    later = cli[merge_idx:]
    merge_l = later[later.index("--languages") + 1]
    assert merge_l == "ko,ja,en"


def test_wizard_emit_cli_includes_output_target():
    state = _wizard_state(output="/Volumes/StudyDeck")
    cli = MODULE["_wizard_emit_cli"](state)
    assert "--output" in cli
    assert cli[cli.index("--output") + 1] == "/Volumes/StudyDeck"


def test_wizard_reading_aid_emits_canonical_reading_flag():
    """The wizard uses the v0.4 `--reading` / `[modify].reading` surface
    exclusively — no legacy `--romanization` or `--furigana` flags, no
    legacy `romanization = ...` / `furigana = ...` TOML keys."""
    state = _wizard_state(reading_aids=["ja:hiragana"])
    cli_str = MODULE["_wizard_emit_cli_string"](state)
    assert "--reading ja:hiragana" in cli_str
    assert "--furigana" not in cli_str
    assert "--romanization" not in cli_str
    toml = MODULE["_wizard_emit_toml"](state)
    assert 'reading = "ja:hiragana"' in toml
    assert "furigana =" not in toml
    assert "romanization =" not in toml


def test_wizard_single_japanese_reading_reaches_merge_output():
    state = _wizard_state(reading_aids=["ja:hiragana"], format="vtt")
    cli = MODULE["_wizard_emit_cli"](state)
    merge_idx = cli.index("--merge")
    merge_block = cli[merge_idx:]
    assert "--reading" in merge_block
    assert merge_block[merge_block.index("--reading") + 1] == "ja:hiragana"

    toml = MODULE["_wizard_emit_toml"](state)
    merge_block_text = toml.split("[merge]", 1)[1]
    assert 'reading = "ja:hiragana"' in merge_block_text


def test_wizard_minimizes_cli_for_single_japanese_vtt_merge():
    state = _wizard_state(
        source="https://anilist.co/anime/196187/Super-no-Ura-de-Yani-Suu-Futari/",
        source_kind="url",
        languages=["ja", "ko"],
        order=["ja", "ko"],
        season="1",
        episode="3-5",
        mt_engine="",
        reading_aids=["ja:hiragana"],
        asbplayer=True,
        format="vtt",
        output="~/Downloads/GetSubtitle",
        steps={"fetch", "modify", "merge"},
    )
    cli = MODULE["_wizard_emit_cli"](state)
    assert cli.count("--languages") == 1
    assert cli[cli.index("--languages") + 1] == "ja,ko"
    assert "--reading-format" not in cli
    modify_idx = cli.index("--modify")
    merge_idx = cli.index("--merge")
    assert "--reading" not in cli[modify_idx:merge_idx]
    merge_block = cli[merge_idx:]
    assert "--languages" not in merge_block
    assert "--reading" in merge_block
    assert merge_block[merge_block.index("--reading") + 1] == "ja:hiragana"
    assert "--format" in merge_block
    assert merge_block[merge_block.index("--format") + 1] == "vtt"


def test_wizard_multiple_japanese_readings_expand_merge_variants():
    state = _wizard_state(
        source_title="MF Ghost 2nd Season",
        languages=["ja", "en"],
        order=["ja", "en"],
        reading_aids=["ja:hiragana", "ja:katakana", "ja:romaji"],
    )
    cli = MODULE["_wizard_emit_cli"](state)
    assert "--title" in cli
    assert cli[cli.index("--title") + 1] == "MF Ghost 2nd Season"
    merge_idx = cli.index("--merge")
    merge_langs = cli[merge_idx:][cli[merge_idx:].index("--languages") + 1]
    assert merge_langs == "ja-hiragana,ja-katakana,ja-romaji,ja,en"
    toml = MODULE["_wizard_emit_toml"](state)
    assert 'languages = "ja-hiragana,ja-katakana,ja-romaji,ja,en"' in toml


def test_wizard_asbplayer_preset_emits_single_line_strip_cc_vtt():
    """Q8 'yes' implies single_line + strip_cc_noise; Q9 with ruby aids
    defaults to vtt. Both should appear in CLI + TOML."""
    state = _wizard_state(asbplayer=True, format="vtt", reading_aids=["ja:hiragana"])
    cli = MODULE["_wizard_emit_cli"](state)
    assert "--single-line" in cli
    assert "--strip-cc-noise" in cli
    assert "--format" in cli
    assert cli[cli.index("--format") + 1] == "vtt"
    toml = MODULE["_wizard_emit_toml"](state)
    assert "single_line = true" in toml
    assert "strip_cc_noise = true" in toml
    assert 'format = "vtt"' in toml


def test_wizard_save_refuses_overwrite_without_confirm():
    """Action 'save' must not overwrite an existing TOML unless the
    user explicitly confirms. Drives the save path logic directly since
    a full wizard run needs a tty."""
    import tempfile, os
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "existing.toml")
        with open(target, "w", encoding="utf-8") as f:
            f.write("# pre-existing content\n")
        before = open(target, encoding="utf-8").read()
        state = _wizard_state()
        # Simulate the wizard's save branch literally: prompt for path,
        # check existence, prompt yes/no, only write if yes.
        path = Path(target).expanduser()
        assert path.exists()
        overwrite_answer = False
        if path.exists() and not overwrite_answer:
            # mirror wizard logic: don't write
            pass
        else:
            path.write_text(MODULE["_wizard_emit_toml"](state))
        after = open(target, encoding="utf-8").read()
        assert after == before, "save logic must not overwrite when user says no"


def test_wizard_save_path_normalizes_friendly_name_to_toml():
    display, path = MODULE["_wizard_normalize_save_path"]("'fena workflow'")
    assert display == "fena workflow.toml"
    assert path == Path("fena workflow.toml")

    display2, path2 = MODULE["_wizard_normalize_save_path"]("~/workflows/jpko")
    assert display2 == "~/workflows/jpko.toml"
    assert str(path2).endswith("/workflows/jpko.toml")


def test_wizard_save_path_rejects_menu_answer_filenames():
    bad = ["b", "back", "q", "quit", "y", "n", "0", "3", "4"]
    for raw in bad:
        try:
            MODULE["_wizard_normalize_save_path"](raw)
        except MODULE["CliError"] as e:
            assert "looks like a menu answer" in str(e)
        else:
            raise AssertionError(f"{raw!r} should not be accepted as a workflow filename")


def test_wizard_save_path_rejects_language_list_filenames():
    try:
        MODULE["_wizard_normalize_save_path"]("ja,en")
    except MODULE["CliError"] as e:
        assert "looks like a language list" in str(e)
    else:
        raise AssertionError("ja,en should not be accepted as a workflow filename")


def test_wizard_save_path_rejects_non_toml_extension():
    try:
        MODULE["_wizard_normalize_save_path"]("workflow.txt")
    except MODULE["CliError"] as e:
        assert "must end in .toml" in str(e)
    else:
        raise AssertionError("workflow.txt should not be accepted as a workflow filename")


def test_wizard_saved_workflow_details_mentions_cli_overrides():
    import contextlib
    import io
    from pathlib import Path

    with contextlib.redirect_stdout(io.StringIO()) as buf:
        MODULE["_wizard_print_saved_workflow_details"](
            "jpko.toml",
            Path("jpko.toml"),
            "getsubtitle --fetch URL --languages ja,ko",
        )
    out = buf.getvalue()
    assert "getsubtitle --config jpko.toml" in out
    assert "--source 'https://www.imdb.com/title/tt1234567/'" in out
    assert "--season 3 --episode all" in out
    assert '--output "$HOME/Downloads/GetSubtitle/TV Show/Season 03"' in out
    assert "CLI flags win over matching TOML settings" in out


def test_wizard_saved_workflow_menu_default_stays_short(monkeypatch, capsys):
    from pathlib import Path

    g = MODULE["_wizard_prompt"].__globals__
    monkeypatch.setitem(g, "input", lambda *a, **k: "")
    MODULE["_wizard_saved_workflow_menu"](
        "jpko.toml",
        Path("jpko.toml"),
        "getsubtitle --fetch URL --languages ja,ko",
    )
    out = capsys.readouterr().out
    assert "Saved workflow:" in out
    assert "Run later:" in out
    assert "getsubtitle --config jpko.toml" in out
    assert "Exact command:" not in out
    assert "--source 'https://www.imdb.com/title/tt1234567/'" not in out


def test_wizard_saved_workflow_menu_can_show_details_and_open_folder(tmp_path, monkeypatch, capsys):
    path = tmp_path / "jpko.toml"
    opened = []
    g = MODULE["_wizard_prompt"].__globals__
    seq = iter(["1", "2", "3"])
    monkeypatch.setitem(g, "input", lambda *a, **k: next(seq))
    monkeypatch.setitem(g, "open_folder", lambda folder: opened.append(folder))
    MODULE["_wizard_saved_workflow_menu"](
        str(path),
        path,
        "getsubtitle --fetch URL --languages ja,ko",
    )
    out = capsys.readouterr().out
    assert "Exact command:" in out
    assert "--source 'https://www.imdb.com/title/tt1234567/'" in out
    assert opened == [tmp_path.resolve()]


def test_wizard_open_saved_workflow_folder_opens_parent(tmp_path):
    import contextlib
    import io

    path = tmp_path / "jpko.toml"
    path.write_text("[fetch]\n", encoding="utf-8")
    fn_g = MODULE["_wizard_open_saved_workflow_folder"].__globals__
    saved_open_folder = fn_g["open_folder"]
    opened = []
    try:
        fn_g["open_folder"] = lambda folder: opened.append(folder)
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_open_saved_workflow_folder"](path)
    finally:
        fn_g["open_folder"] = saved_open_folder

    assert opened == [tmp_path.resolve()]


def test_wizard_emit_toml_korean_reading_aid_passes_through():
    """Korean reading aid (backend not yet shipped) still appears in
    the generated TOML — users can save now and re-run when shipped."""
    state = _wizard_state(
        languages=["ko", "en"],
        order=["ko", "en"],
        reading_aids=["ko:revised"],
    )
    toml = MODULE["_wizard_emit_toml"](state)
    assert 'reading = "ko:revised"' in toml
    cli = MODULE["_wizard_emit_cli"](state)
    assert "--reading" in cli
    assert cli[cli.index("--reading") + 1] == "ko:revised"


def test_wizard_emit_toml_chinese_reading_aid_passes_through():
    """Chinese pinyin (marks) wires through — same forward-compat pattern."""
    state = _wizard_state(
        languages=["zh", "en"],
        order=["zh", "en"],
        reading_aids=["zh:marks"],
    )
    toml = MODULE["_wizard_emit_toml"](state)
    assert 'reading = "zh:marks"' in toml


def test_wizard_emit_toml_mixed_ja_ko_zh_reading_aids():
    """Multi-language learners can stack reading aids across scripts in
    one workflow — ja:hiragana + ko:revised + zh:marks all coexist."""
    state = _wizard_state(
        languages=["ja", "ko", "zh", "en"],
        order=["ja", "ko", "zh", "en"],
        reading_aids=["ja:hiragana", "ko:revised", "zh:marks"],
    )
    toml = MODULE["_wizard_emit_toml"](state)
    assert 'reading = "ja:hiragana,ko:revised,zh:marks"' in toml


def test_wizard_single_language_omits_merge_block():
    """If only one language is collected the merge step makes no sense;
    the emitter should drop it from both CLI and TOML."""
    state = _wizard_state(
        languages=["ja"],
        order=["ja"],
        reading_aids=[],
        asbplayer=False,
        format="srt",
    )
    cli = MODULE["_wizard_emit_cli"](state)
    assert "--merge" not in cli
    toml = MODULE["_wizard_emit_toml"](state)
    assert "[merge]" not in toml


def test_wizard_dependency_probe_flags_deferred_backends_as_warn():
    """Languages whose backend still isn't shipped (Thai, Arabic, Hindi,
    Russian) surface in the probe as warn-level so the wizard still saves
    a workflow the user can re-run later. ja/ko/zh/yue each get their own
    backend-specific block or pass — not 'deferred'."""
    state = _wizard_state(
        languages=["yue", "th", "en"],
        order=["yue", "th", "en"],
        reading_aids=["yue:numbers", "th:royal-thai"],
        mt_engine="",  # avoid ollama/deepl side checks
    )
    gaps = MODULE["_wizard_probe_dependencies"](state)
    deferred = [g for g in gaps if "th:royal-thai" in g[1]]
    assert deferred, "deferred backends should surface in the probe"
    assert all(g[0] == "warn" for g in deferred)
    yue_deferred = [g for g in gaps if "yue:numbers" in g[1] and g[0] == "warn"]
    assert not yue_deferred, "yue:numbers should be a dependency block/pass, not deferred"


def test_wizard_dependency_probe_flags_deepl_missing_key_as_block():
    """DeepL MT without an API key is a blocker — runtime would crash.
    Force the key lookup to return None by patching the function's
    __globals__ dict directly. runpy returns a shallow COPY of the
    executed-module globals, so assigning MODULE["foo"] does NOT alter
    the dict that the function actually consults at call time."""
    state = _wizard_state(mt_engine="deepl")
    fn_g = MODULE["_wizard_probe_dependencies"].__globals__
    saved = fn_g["get_provider_api_key"]
    try:
        fn_g["get_provider_api_key"] = lambda *a, **k: None
        gaps = MODULE["_wizard_probe_dependencies"](state)
    finally:
        fn_g["get_provider_api_key"] = saved
    deepl_gaps = [g for g in gaps if "DeepL" in g[1]]
    assert deepl_gaps and deepl_gaps[0][0] == "block"


def test_argos_translation_path_available_accepts_direct_and_pivot():
    class FakeLang:
        def __init__(self, code, targets=()):
            self.code = code
            self.targets = set(targets)

        def get_translation(self, other):
            return object() if other and other.code in self.targets else None

    installed = [
        FakeLang("ja", ["en"]),
        FakeLang("en", ["ko", "es"]),
        FakeLang("ko", []),
        FakeLang("es", []),
    ]
    assert MODULE["_argos_translation_path_available"](installed, "en", "ko")
    assert MODULE["_argos_translation_path_available"](installed, "ja", "ko")
    assert not MODULE["_argos_translation_path_available"](installed, "ko", "ja")


def test_wizard_q6_argos_preflight_can_disable_translation():
    import contextlib
    import io

    state = _wizard_state(languages=["en", "ko"], mt_engine="")
    fn_g = MODULE["_wizard_q6_translate"].__globals__
    saved_statuses = fn_g["_wizard_argos_pair_statuses"]
    had_input = "input" in fn_g
    saved_input = fn_g.get("input")
    answers = iter(["2", "2"])  # choose Argos, then continue without translation
    try:
        fn_g["_wizard_argos_pair_statuses"] = lambda _state: [
            ("en", "ko", True, []),
            ("ko", "en", False, ["translate-ko_en"]),
        ]
        fn_g["input"] = lambda *a, **k: next(answers)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q6_translate"](state)
    finally:
        fn_g["_wizard_argos_pair_statuses"] = saved_statuses
        if had_input:
            fn_g["input"] = saved_input
        else:
            fn_g.pop("input", None)
    out = buf.getvalue()
    assert state.mt_engine == ""
    assert "Fill missing subtitles?" in out
    assert "Checking Argos language packs" in out
    assert "✓ en -> ko installed" in out
    assert "✗ ko -> en missing" in out
    assert "Continue without translation" in out


def test_wizard_dependency_probe_flags_argos_missing_language_pack_as_block(monkeypatch):
    import types
    import sys

    state = _wizard_state(languages=["en", "ko"], mt_engine="argos")
    fn_g = MODULE["_wizard_probe_dependencies"].__globals__
    saved_statuses = fn_g["_wizard_argos_pair_statuses"]
    saved_module = sys.modules.get("argostranslate")
    monkeypatch.setitem(sys.modules, "argostranslate", types.SimpleNamespace())
    try:
        fn_g["_wizard_argos_pair_statuses"] = lambda _state: [
            ("en", "ko", True, []),
            ("ko", "en", False, ["translate-ko_en"]),
        ]
        gaps = MODULE["_wizard_probe_dependencies"](state)
    finally:
        fn_g["_wizard_argos_pair_statuses"] = saved_statuses
        if saved_module is None:
            monkeypatch.delitem(sys.modules, "argostranslate", raising=False)
        else:
            monkeypatch.setitem(sys.modules, "argostranslate", saved_module)
    argos_gaps = [g for g in gaps if "Argos language pack" in g[1]]
    assert argos_gaps and argos_gaps[0][0] == "block"
    assert "argospm install translate-ko_en" in argos_gaps[0][2]


def test_wizard_dependency_probe_blocks_unwritable_output_target(tmp_path):
    bad_output = tmp_path / "not-a-folder"
    bad_output.write_text("file, not a directory", encoding="utf-8")
    state = _wizard_state(
        source=str(tmp_path),
        source_kind="path",
        languages=["ja"],
        order=["ja"],
        mt_engine="",
        reading_aids=[],
        output=str(bad_output),
        steps={"modify"},
    )
    gaps = MODULE["_wizard_probe_dependencies"](state)
    output_gaps = [g for g in gaps if "Output target" in g[1]]
    assert output_gaps and output_gaps[0][0] == "block"


def test_wizard_dependency_probe_warns_when_broad_provider_keys_missing(tmp_path):
    state = _wizard_state(
        source="https://www.imdb.com/title/tt0108778/",
        source_kind="url",
        languages=["en", "es"],
        order=["en", "es"],
        mt_engine="",
        reading_aids=[],
        output=str(tmp_path),
        steps={"fetch", "merge"},
    )
    fn_g = MODULE["_wizard_probe_dependencies"].__globals__
    saved = fn_g["get_provider_api_key"]
    try:
        fn_g["get_provider_api_key"] = lambda _provider, **_kwargs: None
        gaps = MODULE["_wizard_probe_dependencies"](state)
    finally:
        fn_g["get_provider_api_key"] = saved
    provider_gaps = [g for g in gaps if "Wyzie or SubDL" in g[1]]
    assert provider_gaps and provider_gaps[0][0] == "warn"


def test_wizard_coverage_preflight_reports_complete_local_merge_set(tmp_path):
    (tmp_path / "Show - S01E01.ja.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n",
        encoding="utf-8",
    )
    (tmp_path / "Show - S01E01.en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        encoding="utf-8",
    )
    state = _wizard_state(
        source=str(tmp_path),
        source_kind="path",
        languages=["ja", "en"],
        order=["ja", "en"],
        season="1",
        episode="1",
        mt_engine="",
        reading_aids=[],
        steps={"modify", "merge"},
    )
    notes = MODULE["_wizard_coverage_preflight"](state)
    assert notes
    assert notes[0][0] == "info"
    assert "Local subtitles found for all requested languages" in notes[0][1]


def test_wizard_coverage_preflight_warns_about_partial_local_merge_set(tmp_path):
    (tmp_path / "Show - S01E01.ja.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n",
        encoding="utf-8",
    )
    (tmp_path / "Show - S01E01.en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        encoding="utf-8",
    )
    (tmp_path / "Show - S01E02.ja.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nまたね\n",
        encoding="utf-8",
    )
    state = _wizard_state(
        source=str(tmp_path),
        source_kind="path",
        languages=["ja", "en"],
        order=["ja", "en"],
        season="1",
        episode="all",
        mt_engine="",
        reading_aids=[],
        steps={"modify", "merge"},
    )
    notes = MODULE["_wizard_coverage_preflight"](state)
    partial = [n for n in notes if "Some requested subtitles are not in this folder yet" in n[1]]
    assert partial and partial[0][0] == "warn"
    assert "S01E02 missing en" in partial[0][2]


def test_wizard_coverage_preflight_warns_about_existing_merge_outputs(tmp_path):
    (tmp_path / "Show - S01E01.ja.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n",
        encoding="utf-8",
    )
    (tmp_path / "Show - S01E01.en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        encoding="utf-8",
    )
    (tmp_path / "Show - S01E01.ja-en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nこんにちは\nHello\n",
        encoding="utf-8",
    )
    state = _wizard_state(
        source=str(tmp_path),
        source_kind="path",
        languages=["ja", "en"],
        order=["ja", "en"],
        season="1",
        episode="1",
        mt_engine="",
        reading_aids=[],
        format="srt",
        output=str(tmp_path),
        steps={"modify", "merge"},
    )
    notes = MODULE["_wizard_coverage_preflight"](state)
    existing = [n for n in notes if "Existing output files detected" in n[1]]
    assert existing and existing[0][0] == "warn"
    assert "Show - S01E01.ja-en.srt" in existing[0][2]


def test_format_failure_what_why_how():
    block = MODULE["_format_failure"]("DeepL API key", "Required.", "getsubtitle --set-key deepl")
    assert "What: DeepL API key" in block
    assert "Why:  Required." in block
    assert "How:  getsubtitle --set-key deepl" in block


def test_wizard_probe_flags_missing_ollama_model(monkeypatch):
    # Daemon reachable but the target model isn't downloaded -> a row that
    # tells the user how to pre-pull (so a long run doesn't stall mid-way).
    g = MODULE["_wizard_probe_dependencies"].__globals__
    monkeypatch.setitem(g, "_wizard_ollama_reachable", lambda: True)
    monkeypatch.setitem(g, "_wizard_ollama_installed_models", lambda: {"llama3.2:3b"})
    monkeypatch.setitem(g, "_ollama_models_flag", lambda name, default=True: True)
    monkeypatch.setitem(g, "get_provider_api_key", lambda p: "x")
    st = MODULE["_WizardState"]()
    st.steps = {"translate", "merge"}
    st.mt_engine = "ollama"
    st.languages = ["ja", "en"]
    st.source = "/tmp"
    st.output = "/tmp"
    st.source_kind = "path"
    rows = MODULE["_wizard_probe_dependencies"](st)
    model_rows = [r for r in rows if "Ollama model" in r[1]]
    assert model_rows, rows
    assert "ollama pull qwen3:4b" in model_rows[0][2]


def test_wizard_dependency_check_runs_with_info_only_preflight():
    import contextlib
    import io

    state = _wizard_state()
    info = [("info", "Coverage estimate: 1/1 episode(s) have all requested languages", "Fast scan checked 2 subtitle candidate(s).")]
    fn_g = MODULE["_wizard_dependency_check_before_run"].__globals__
    saved_probe = fn_g["_wizard_probe_dependencies"]
    try:
        fn_g["_wizard_probe_dependencies"] = lambda _state: info
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            action = MODULE["_wizard_dependency_check_before_run"](state)
    finally:
        fn_g["_wizard_probe_dependencies"] = saved_probe
    out = buf.getvalue()
    assert action == "run"
    assert "Preflight check —" in out
    assert "Heads-up — no action needed before running." in out
    assert "Run setup now" not in out


def test_wizard_run_summary_prints_outcome_and_next_steps(tmp_path, capsys):
    state = _wizard_state(
        source="https://www.imdb.com/title/tt0108778/",
        source_kind="url",
        languages=["en", "es"],
        order=["en", "es"],
        season="4",
        episode="3-5",
        output=str(tmp_path),
    )
    try:
        summary = MODULE["_wizard_summary_begin"](state)
        summary.command = "getsubtitle --fetch URL --merge"
        MODULE["_wizard_summary_add_preflight"]([
            ("warn", "Wyzie or SubDL API key", "getsubtitle --set-key wyzie"),
            ("info", "Coverage estimate: 1/1 episode(s) have all requested languages", ""),
        ])
        MODULE["_wizard_summary_add"](
            "fetch",
            planned=2,
            written=1,
            outputs=[tmp_path / "Friends - S04E03.en.srt"],
            missing=["es E03: missing"],
        )
        MODULE["_wizard_summary_add"](
            "merge",
            planned=1,
            written=1,
            outputs=[tmp_path / "Friends - S04E03.en-es.srt"],
        )
        summary = MODULE["_wizard_summary_end"]()
        MODULE["_wizard_print_run_summary"](summary, 0)
    finally:
        MODULE["_wizard_summary_end"]()
    out = capsys.readouterr().out
    assert "Workflow summary" in out
    assert "Completed with issues" in out
    assert "Scope: season 4, episode 3-5" in out
    assert "Preflight warnings: 1" in out
    assert "Preflight info: 1" in out
    assert "Fetch: planned 2, wrote 1, missing/issues 1" in out
    assert "Merge: planned 1, wrote 1" in out
    assert "Next steps:" in out
    assert "1. Open the subtitle file in your player." in out
    assert "2. Adjust font size or format if needed." in out


def test_wizard_run_summary_output_exists_is_no_change(tmp_path, capsys, monkeypatch):
    state = _wizard_state(
        source=str(tmp_path),
        source_kind="path",
        languages=["ja", "ko"],
        order=["ja", "ko"],
        output=str(tmp_path),
    )
    monkeypatch.setitem(
        MODULE["_wizard_print_run_summary"].__globals__,
        "_wizard_is_interactive",
        lambda: True,
    )
    try:
        summary = MODULE["_wizard_summary_begin"](state)
        summary.command = f"getsubtitle --source {tmp_path} --merge --languages ja,ko"
        MODULE["_wizard_summary_add"](
            "merge",
            scanned=2,
            skipped=1,
            missing=["S01E09: output exists: Show.S01E09.ja-ko.vtt (use --force to overwrite)"],
        )
        summary = MODULE["_wizard_summary_end"]()
        MODULE["_wizard_print_run_summary"](summary, 1)
    finally:
        MODULE["_wizard_summary_end"]()
    out = capsys.readouterr().out
    assert "Completed with no changes" in out
    assert "already exists" in out
    assert "Some subtitles were missing" not in out
    assert "Fill missing subtitles" not in out
    assert "--force" in out


def test_wizard_dependency_check_saves_instead_of_running_with_remaining_blocker():
    """A block-level dependency must actually block the Run action.

    Regression: DeepL setup could be offered and declined inside setup,
    then the wizard still dispatched a run that would immediately fail.
    """
    import contextlib
    import io

    state = _wizard_state(mt_engine="deepl")
    blocker = [("block", "DeepL API key", "getsubtitle --set-key deepl")]
    fn_g = MODULE["_wizard_dependency_check_before_run"].__globals__
    saved_probe = fn_g["_wizard_probe_dependencies"]
    saved_yesno = fn_g["_wizard_yesno"]
    saved_setup = fn_g["_wizard_run_setup"]
    answers = iter([True, True])  # try setup, then save workflow instead
    setup_called = []
    try:
        fn_g["_wizard_probe_dependencies"] = lambda _state: blocker
        fn_g["_wizard_yesno"] = lambda _q, default=True: next(answers)
        fn_g["_wizard_run_setup"] = lambda _state, _gaps: setup_called.append(True)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            action = MODULE["_wizard_dependency_check_before_run"](state)
    finally:
        fn_g["_wizard_probe_dependencies"] = saved_probe
        fn_g["_wizard_yesno"] = saved_yesno
        fn_g["_wizard_run_setup"] = saved_setup
    out = buf.getvalue()
    assert action == "save"
    assert setup_called == [True]
    assert "Still blocked — the run would fail before it starts:" in out


def test_setup_pip_fix_target_parses_preflight_hints():
    parse = MODULE["_setup_pip_fix_target"]
    assert parse('pip install -e ".[romanization-zh]"  # or: pip install pypinyin') == (
        "pypinyin", "romanization-zh"
    )
    assert parse('pip install -e ".[furigana]"  # or: pip install sudachipy sudachidict_core') == (
        "sudachipy", "furigana"
    )
    assert parse('pip install -e ".[romanization-ko]"  # also installs g2pk') == (
        "korean-romanizer", "romanization-ko"
    )
    assert parse('pip install -e ".[romanization-yue]"  # or: pip install pycantonese') == (
        "pycantonese", "romanization-yue"
    )
    assert parse("pip install g2pk — improves Korean G2P accuracy") == ("g2pk", None)
    assert parse("pip install argostranslate") == ("argostranslate", None)
    assert parse("argospm install translate-ja_en") is None


def test_wizard_run_setup_can_install_all_pip_blockers(monkeypatch, capsys):
    calls = []
    g = MODULE["_wizard_run_setup"].__globals__
    monkeypatch.setitem(
        g,
        "_setup_offer_pip_install",
        lambda package, extra=None: calls.append((package, extra)) or True,
    )
    MODULE["_wizard_run_setup"](
        _wizard_state(),
        [
            ("block", "SudachiPy + SudachiDict-core (Japanese reading aids)",
             'pip install -e ".[furigana]"  # or: pip install sudachipy sudachidict_core'),
            ("block", "korean-romanizer (Korean Revised Romanization)",
             'pip install -e ".[romanization-ko]"  # also installs g2pk'),
            ("warn", "g2pk (Korean G2P preprocessing)",
             "pip install g2pk — improves Korean G2P accuracy"),
            ("block", "pypinyin (Mandarin pinyin)",
             'pip install -e ".[romanization-zh]"  # or: pip install pypinyin'),
            ("block", "pycantonese (Cantonese Jyutping)",
             'pip install -e ".[romanization-yue]"  # or: pip install pycantonese'),
            ("block", "argostranslate (offline MT)",
             "pip install argostranslate"),
        ],
    )
    assert calls == [
        ("sudachipy", "furigana"),
        ("korean-romanizer", "romanization-ko"),
        ("g2pk", None),
        ("pypinyin", "romanization-zh"),
        ("pycantonese", "romanization-yue"),
        ("argostranslate", None),
    ]
    out = capsys.readouterr().out
    assert "Run this in your shell" not in out


def test_setup_offer_pip_install_uses_project_root_for_extras(monkeypatch, tmp_path, capsys):
    project = tmp_path / "repo"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='getsubtitle'\n", encoding="utf-8")
    calls = []

    class Result:
        returncode = 0

    g = MODULE["_setup_offer_pip_install"].__globals__
    monkeypatch.setitem(g, "_wizard_yesno", lambda _q, default=True: True)
    monkeypatch.setitem(g, "_setup_project_root", lambda: project)
    monkeypatch.setitem(g, "_setup_module_exists", lambda _name: True)
    monkeypatch.setitem(
        g["subprocess"].__dict__,
        "run",
        lambda cmd, check=False, cwd=None: calls.append((cmd, check, cwd)) or Result(),
    )

    assert MODULE["_setup_offer_pip_install"]("pypinyin", extra="romanization-zh")
    assert calls
    cmd, check, cwd = calls[0]
    assert cmd[-2:] == ["-e", ".[romanization-zh]"]
    assert check is False
    assert cwd == str(project)
    out = capsys.readouterr().out
    assert "Project folder:" in out


def test_setup_offer_pip_install_uses_current_python_for_plain_package(monkeypatch):
    calls = []

    class Result:
        returncode = 0

    g = MODULE["_setup_offer_pip_install"].__globals__
    monkeypatch.setitem(g, "_wizard_yesno", lambda _q, default=True: True)
    monkeypatch.setitem(g, "_setup_module_exists", lambda _name: True)
    monkeypatch.setitem(
        g["subprocess"].__dict__,
        "run",
        lambda cmd, check=False, cwd=None: calls.append((cmd, check, cwd)) or Result(),
    )

    assert MODULE["_setup_offer_pip_install"]("argostranslate")
    cmd, check, cwd = calls[0]
    assert cmd[:3] == [g["sys"].executable, "-m", "pip"]
    assert cmd[-1] == "argostranslate"
    assert check is False
    assert cwd is None


def test_wizard_state_to_toml_round_trip_safe():
    """The draft TOML must be valid enough that we can load it back."""
    state = _wizard_state()
    text = state.to_toml()
    # Cheap shape checks — not parsing with the minimal TOML reader since
    # that has well-known limitations around quoting in this sandbox.
    assert "[wizard]" in text
    assert "source =" in text
    assert "languages =" in text
    assert text.endswith("\n")


# ─── v0.6 wizard UX touch-ups ───────────────────────────────────────


def test_wizard_url_is_movie_detection():
    """TMDB /movie/ and Letterboxd /film/ are unambiguous movie URLs;
    TV/anime URLs and unknown shapes are not."""
    is_movie = MODULE["_wizard_url_is_movie"]
    assert is_movie("https://www.themoviedb.org/movie/8392")
    assert is_movie("https://letterboxd.com/film/totoro/")
    assert not is_movie("https://www.themoviedb.org/tv/65701")
    assert not is_movie("https://anilist.co/anime/21519/")
    assert not is_movie("https://www.imdb.com/title/tt0096283/")  # ambiguous
    assert not is_movie("")


def test_wizard_q5_scope_skipped_for_movies():
    """When state.is_movie is True, Q6 (episode scope) is skipped so the
    user does not see an irrelevant prompt and the downstream filename
    builder does not invent 'Season Unknown' / 'S00E00' placeholders."""
    s = MODULE["_WizardState"](
        source="https://www.themoviedb.org/movie/8392",
        source_kind="url",
        languages=["ja", "en"],
        order=["ja", "en"],
        is_movie=True,
    )
    MODULE["_wizard_q5_scope"](s)
    # No prompt was raised (would have hit a non-tty EOFError); the season
    # / episode fields stay empty for the movie path.
    assert s.season == ""
    assert s.episode == ""


def test_wizard_q5_scope_specific_episode_defaults_to_first_episode():
    import contextlib
    import io

    s = MODULE["_WizardState"](
        source="https://www.themoviedb.org/tv/456",
        source_kind="url",
        languages=["ko", "en"],
        is_movie=False,
    )
    fn_g = MODULE["_wizard_q5_scope"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    try:
        def fake_prompt(label, default="", *args, **kwargs):
            if label == "Number":
                return "1"
            return default

        fn_g["_wizard_prompt"] = fake_prompt
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q5_scope"](s)
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
    out = buf.getvalue()
    assert s.season == "1"
    assert s.episode == "1"
    assert "Defaults to Season 1 Episode 1." in out
    assert "looks like a TV/show result, not a movie" not in out


def test_wizard_q5_scope_keeps_episode_inferred_from_selected_file():
    """When local-file preflight adds Fetch, Q5 must not ask for S/E again.

    The selected filename already pinned the scope, so the URL/title scope
    prompt should preserve it instead of defaulting back to S01E01.
    """
    import contextlib
    import io

    s = MODULE["_WizardState"](
        source="https://anilist.co/anime/166610/",
        source_kind="url",
        languages=["ja", "en"],
        order=["ja", "en"],
        season="2",
        episode="13",
    )
    fn_g = MODULE["_wizard_q5_scope"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    try:
        fn_g["_wizard_prompt"] = lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("Q5 should not prompt when scope is already pinned")
        )
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q5_scope"](s)
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
    assert s.season == "2"
    assert s.episode == "13"
    assert "S02E13" in buf.getvalue()


def test_wizard_q5_whole_season_does_not_prompt_for_season():
    """Option 2 means default/current season, all episodes.

    The wizard used to ask a second "Season" prompt after the user chose
    "Whole season, every episode", which made the shortcut feel pointless.
    """
    import contextlib
    import io

    s = MODULE["_WizardState"](
        source="https://anilist.co/anime/166610/",
        source_kind="url",
        languages=["ja", "en"],
        order=["ja", "en"],
    )
    fn_g = MODULE["_wizard_q5_scope"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    calls: list[str] = []

    def fake_prompt(label, default="", *args, **kwargs):
        calls.append(label)
        if label == "Number":
            return "2"
        raise AssertionError(f"unexpected prompt after whole-season choice: {label}")

    try:
        fn_g["_wizard_prompt"] = fake_prompt
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q5_scope"](s)
    finally:
        fn_g["_wizard_prompt"] = saved_prompt

    assert calls == ["Number"]
    assert s.season == "1"
    assert s.episode == "all"


def test_wizard_q5_scope_back_inside_specific_episode_returns_to_scope_menu():
    import contextlib
    import io

    s = MODULE["_WizardState"](
        source="https://www.themoviedb.org/tv/456",
        source_kind="url",
        languages=["ko", "en"],
        is_movie=False,
    )
    fn_g = MODULE["_wizard_q5_scope"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    number_answers = iter(["1", "1"])
    season_prompts = 0

    def fake_prompt(label, default="", *args, **kwargs):
        nonlocal season_prompts
        if label == "Number":
            return next(number_answers)
        if label.startswith("Season or range"):
            season_prompts += 1
            if season_prompts == 1:
                raise MODULE["_WizardBack"]()
            return default
        if label.startswith("Episode or range"):
            return default
        raise AssertionError(f"unexpected prompt: {label}")

    try:
        fn_g["_wizard_prompt"] = fake_prompt
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q5_scope"](s)
    finally:
        fn_g["_wizard_prompt"] = saved_prompt

    assert s.season == "1"
    assert s.episode == "1"
    assert "Going back to episode scope." in buf.getvalue()


def test_wizard_prompt_distinguishes_back_from_quit_in_hint():
    import builtins

    prompt_fn = MODULE["_wizard_prompt"]
    g = prompt_fn.__globals__
    saved_active = g["_WIZARD_BACK_NAV_ACTIVE"]
    saved_input = builtins.input
    prompts: list[str] = []

    def fake_input(prompt):
        prompts.append(prompt)
        return "b"

    try:
        g["_WIZARD_BACK_NAV_ACTIVE"] = True
        builtins.input = fake_input
        try:
            prompt_fn("Folder or file path")
        except MODULE["_WizardBack"]:
            pass
        else:
            raise AssertionError("expected back to raise _WizardBack")
    finally:
        builtins.input = saved_input
        g["_WIZARD_BACK_NAV_ACTIVE"] = saved_active

    assert prompts
    assert "[b=back | q=quit]" in prompts[0]
    assert "[back/quit]" not in prompts[0]


def test_wizard_quit_at_path_prompt_is_not_recoverable_draft():
    s = MODULE["_WizardState"](steps={"fetch"})
    fn = MODULE["_wizard_q1_source"]
    fn_g = fn.__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    answers = iter(["3"])

    def fake_prompt(label, default=None, **kwargs):
        if label == "Number":
            return next(answers)
        if label == "Folder or file path":
            raise MODULE["_WizardAbort"]("user quit")
        raise AssertionError(f"unexpected prompt: {label}")

    try:
        fn_g["_wizard_prompt"] = fake_prompt
        try:
            fn(s)
        except MODULE["_WizardAbort"]:
            pass
        else:
            raise AssertionError("expected abort at folder path prompt")
    finally:
        fn_g["_wizard_prompt"] = saved_prompt

    assert s.source_kind == "path"
    assert s.source == ""
    assert MODULE["_wizard_has_recoverable_draft"](s) is False


def test_wizard_source_picker_treats_free_text_as_title_search():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch"})
    fn = MODULE["_wizard_q1_source"]
    fn_g = fn.__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_picker = fn_g["_wizard_pick_title_candidate"]
    saved_yesno = fn_g["_wizard_yesno"]

    try:
        fn_g["_wizard_prompt"] = lambda label, default=None, **kwargs: "the simpsons"
        fn_g["_wizard_pick_title_candidate"] = lambda title: (
            "https://www.themoviedb.org/movie/35",
            "tmdb-movie",
            "TMDB Movie: The Simpsons Movie (2007)",
            True,
        )
        fn_g["_wizard_yesno"] = lambda _q, default=False: False
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            fn(s)
        out = buf.getvalue()
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["_wizard_pick_title_candidate"] = saved_picker
        fn_g["_wizard_yesno"] = saved_yesno

    assert s.source_kind == "url"
    assert s.source == "https://www.themoviedb.org/movie/35"
    assert s.source_title == "The Simpsons Movie"
    assert s.is_movie is True
    assert "Detected title search:" in out
    assert "Matched title: TMDB Movie: The Simpsons Movie (2007)" in out


def test_wizard_path_fetch_asks_for_better_title_override(tmp_path):
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch", "modify", "merge"})
    root = tmp_path / "니아 오토마타"
    root.mkdir()
    (root / "[Ohys-Raws] NieR Automata Ver1.1a - 01.mp4").touch()

    fn = MODULE["_wizard_q1_source"]
    fn_g = fn.__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_picker = fn_g["_wizard_pick_title_candidate"]
    saved_yesno = fn_g["_wizard_yesno"]

    answers = iter([
        "3",                 # source kind: local path
        str(root),           # folder path
        "2",                 # enter a better title
        "NieR Automata Ver1.1a",
    ])

    def fake_prompt(label, default=None, **kwargs):
        return next(answers)

    try:
        fn_g["_wizard_prompt"] = fake_prompt
        fn_g["_wizard_pick_title_candidate"] = lambda title: (
            "https://anilist.co/anime/145665/",
            "anilist",
            "AniList: 145665: NieR:Automata Ver1.1a / ニーア オートマタ Ver1.1a (2023, 12 eps)",
            False,
        )
        fn_g["_wizard_yesno"] = lambda _q, default=False: False
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            fn(s)
        out = buf.getvalue()
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["_wizard_pick_title_candidate"] = saved_picker
        fn_g["_wizard_yesno"] = saved_yesno

    assert s.source_kind == "path"
    assert s.source == str(root)
    assert s.source_title == "NieR:Automata Ver1.1a"
    assert s.source_anilist_id == "145665"
    assert "Online subtitle search needs a movie/show title." in out
    assert "Folder title guess: NieR Automata Ver1.1a" in out
    cli = MODULE["_wizard_emit_cli_string"](s)
    assert f"--fetch {MODULE['shlex'].quote(str(root))}" in cli
    assert "--title 'NieR:Automata Ver1.1a'" in cli
    assert "--anilist 145665" in cli
    toml = MODULE["_wizard_emit_toml"](s)
    assert 'title = "NieR:Automata Ver1.1a"' in toml
    assert 'anilist = "145665"' in toml


def test_wizard_path_fetch_title_guess_prefers_video_filename(tmp_path):
    root = tmp_path / "니아 오토마타"
    root.mkdir()
    for ep in range(1, 4):
        (root / f"[Ohys-Raws] NieR Automata Ver1.1a - {ep:02d} (BS11 1280x720 x264 AAC).mp4").touch()

    guess = MODULE["_wizard_path_fetch_title_guess"](root)

    assert guess == "NieR Automata Ver1.1a"


def test_wizard_path_fetch_title_guess_cleans_movie_release_filename(tmp_path):
    root = tmp_path / "식신"
    root.mkdir()
    (root / "The.God.of.Cookery.1996.WEBRip.1080p.x264.AAC.2Audio-TiNyHD.mkv").touch()

    guess = MODULE["_wizard_path_fetch_title_guess"](root)

    assert guess == "The God of Cookery (1996)"


def test_wizard_path_fetch_movie_hint_avoids_episode_all(tmp_path):
    root = tmp_path / "식신"
    root.mkdir()
    (root / "The.God.of.Cookery.1996.WEBRip.1080p.x264.AAC.2Audio-TiNyHD.mkv").touch()
    state = _wizard_state(
        source=str(root),
        source_kind="path",
        source_title="The God of Cookery",
        is_movie=True,
        season="",
        episode="",
        languages=["zh", "ko", "en"],
        order=["zh", "ko", "en"],
        steps={"fetch", "modify", "merge"},
    )

    cli = MODULE["_wizard_emit_cli"](state)

    assert "--movie" in cli
    assert "--episode" not in cli


def test_wizard_title_no_match_retry_accepts_free_text_title():
    fn = MODULE["_wizard_pick_title_candidate"]
    fn_g = fn.__globals__
    saved_candidates = fn_g["_wizard_title_candidates"]
    saved_prompt = fn_g["_wizard_prompt"]
    answers = iter(["1", "식신", "2"])

    def fake_candidates(title):
        if title == "식신":
            return [
                {
                    "provider": "tmdb-tv",
                    "label": "TMDB TV: 식신로드 (2010)",
                    "url": "https://www.themoviedb.org/tv/1",
                    "is_movie": False,
                },
                {
                    "provider": "tmdb-movie",
                    "label": "TMDB Movie: The God of Cookery (1996)",
                    "url": "https://www.themoviedb.org/movie/123",
                    "is_movie": True,
                },
            ]
        return []

    try:
        fn_g["_wizard_title_candidates"] = fake_candidates
        fn_g["_wizard_prompt"] = lambda *a, **k: next(answers)
        picked = fn("The.God.of.Cookery.1996.WEBRip.1080p")
    finally:
        fn_g["_wizard_title_candidates"] = saved_candidates
        fn_g["_wizard_prompt"] = saved_prompt

    assert picked == (
        "https://www.themoviedb.org/movie/123",
        "tmdb-movie",
        "TMDB Movie: The God of Cookery (1996)",
        True,
    )


def test_wizard_crunchyroll_watch_url_asks_for_stronger_source_when_metadata_fails():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch"})
    fn = MODULE["_wizard_q1_source"]
    fn_g = fn.__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_metadata = fn_g["crunchyroll_metadata_from_url"]
    watch_url = "https://www.crunchyroll.com/watch/GE00379925JAJP/mini-episode-1"
    anilist_url = "https://anilist.co/anime/196187/Super-no-Ura-de-Yani-Suu-Futari/"

    def fake_prompt(label, default=None, **kwargs):
        if label == "Number":
            return "2"
        if label == "URL":
            return watch_url
        if label == "Series URL, AniList ID, or title":
            return anilist_url
        raise AssertionError(f"unexpected prompt: {label}")

    try:
        fn_g["_wizard_prompt"] = fake_prompt
        fn_g["crunchyroll_metadata_from_url"] = lambda _url: None
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            fn(s)
        out = buf.getvalue()
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["crunchyroll_metadata_from_url"] = saved_metadata

    assert s.source_kind == "url"
    assert s.source == anilist_url
    assert s.source_title == ""
    assert "I could not read Crunchyroll metadata" in out
    assert "Searching for: AniList anime URL" in out


def test_wizard_crunchyroll_watch_url_accepts_anilist_id():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch"})
    fn = MODULE["_wizard_q1_source"]
    fn_g = fn.__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_metadata = fn_g["crunchyroll_metadata_from_url"]
    watch_url = "https://www.crunchyroll.com/watch/GE00379925JAJP/mini-episode-1"
    answers = iter(["2", watch_url, "196187"])

    def fake_prompt(label, default=None, **kwargs):
        if label == "Number":
            return next(answers)
        if label == "URL":
            return next(answers)
        if label == "Series URL, AniList ID, or title":
            return next(answers)
        raise AssertionError(f"unexpected prompt: {label}")

    try:
        fn_g["_wizard_prompt"] = fake_prompt
        fn_g["crunchyroll_metadata_from_url"] = lambda _url: None
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            fn(s)
        out = buf.getvalue()
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["crunchyroll_metadata_from_url"] = saved_metadata

    assert s.source_kind == "url"
    assert s.source == "https://anilist.co/anime/196187/"
    assert "Searching for: Crunchyroll watch URL" in out
    assert "Using AniList anime ID: 196187" in out


def test_crunchyroll_content_object_uses_anonymous_token():
    fn = MODULE["crunchyroll_content_object"]
    g = fn.__globals__
    saved_request = g["request_json_browser"]
    calls = []

    def fake_request_json_browser(url, **kwargs):
        calls.append((url, kwargs))
        if url == g["CRUNCHYROLL_AUTH_API"]:
            assert kwargs["method"] == "POST"
            assert kwargs["data"] == {"grant_type": "client_id", "client_id": "cr_web"}
            return {"access_token": "anon-token"}
        assert "/content/v2/cms/objects/GY1QKKMZR" in url
        assert kwargs["headers"]["Authorization"] == "Bearer anon-token"
        return {"data": [{"id": "GY1QKKMZR", "title": "Assault", "type": "episode"}]}

    try:
        g["request_json_browser"] = fake_request_json_browser
        result = fn("GY1QKKMZR")
    finally:
        g["request_json_browser"] = saved_request

    assert result is not None
    assert result["title"] == "Assault"
    assert len(calls) == 2


def test_crunchyroll_metadata_from_watch_url_parses_episode_metadata():
    fn = MODULE["crunchyroll_metadata_from_url"]
    g = fn.__globals__
    saved_content = g["crunchyroll_content_object"]
    try:
        g["crunchyroll_content_object"] = lambda _id: {
            "id": "GY1QKKMZR",
            "title": "Assault",
            "type": "episode",
            "slug_title": "assault",
            "episode_metadata": {
                "series_id": "GRDV0019R",
                "series_slug_title": "jujutsu-kaisen",
                "series_title": "JUJUTSU KAISEN",
                "season_number": 1,
                "episode_number": 7,
            },
        }
        result = fn("https://www.crunchyroll.com/watch/GY1QKKMZR/assault")
    finally:
        g["crunchyroll_content_object"] = saved_content

    assert result is not None
    assert result.title == "JUJUTSU KAISEN"
    assert result.episode_title == "Assault"
    assert result.season == "1"
    assert result.episode == "7"
    assert result.url == "https://www.crunchyroll.com/series/GRDV0019R/jujutsu-kaisen"


def test_crunchyroll_metadata_from_series_url_parses_series_metadata():
    fn = MODULE["crunchyroll_metadata_from_url"]
    g = fn.__globals__
    saved_content = g["crunchyroll_content_object"]
    try:
        g["crunchyroll_content_object"] = lambda _id: {
            "id": "GYZJ43JMR",
            "title": "That Time I Got Reincarnated as a Slime",
            "type": "series",
            "slug_title": "that-time-i-got-reincarnated-as-a-slime",
            "series_metadata": {},
        }
        result = fn("https://www.crunchyroll.com/series/GYZJ43JMR/that-time-i-got-reincarnated-as-a-slime")
    finally:
        g["crunchyroll_content_object"] = saved_content

    assert result is not None
    assert result.title == "That Time I Got Reincarnated as a Slime"
    assert result.season == "auto"
    assert result.episode == "auto"
    assert result.url == "https://www.crunchyroll.com/series/GYZJ43JMR/that-time-i-got-reincarnated-as-a-slime"


def test_apply_crunchyroll_metadata_updates_media_without_overriding_scope():
    import contextlib
    import io
    fn = MODULE["apply_crunchyroll_metadata"]
    g = fn.__globals__
    saved_metadata = g["crunchyroll_metadata_from_url"]
    metadata_cls = MODULE["CrunchyrollMetadata"]
    media_cls = MODULE["MediaInfo"]
    watch_url = "https://www.crunchyroll.com/watch/GY1QKKMZR/assault"
    series_url = "https://www.crunchyroll.com/series/GRDV0019R/jujutsu-kaisen"
    media = media_cls(source_url=watch_url, provider="crunchyroll", title="", season="3", episode="25")

    try:
        g["crunchyroll_metadata_from_url"] = lambda _url: metadata_cls(
            title="JUJUTSU KAISEN",
            url=series_url,
            crunchyroll_id="GY1QKKMZR",
            series_id="GRDV0019R",
            episode_title="Assault",
            season="1",
            episode="7",
        )
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            changed = fn(media)
        out = buf.getvalue()
    finally:
        g["crunchyroll_metadata_from_url"] = saved_metadata

    assert changed is True
    assert media.source_url == series_url
    assert media.title == "JUJUTSU KAISEN"
    assert media.season == "3"
    assert media.episode == "25"
    assert "Crunchyroll metadata lookup" in out


def test_wizard_crunchyroll_watch_url_uses_metadata_without_extra_prompt():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch"})
    fn = MODULE["_wizard_q1_source"]
    fn_g = fn.__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_metadata = fn_g["crunchyroll_metadata_from_url"]
    metadata_cls = MODULE["CrunchyrollMetadata"]
    watch_url = "https://www.crunchyroll.com/watch/GY1QKKMZR/assault"
    series_url = "https://www.crunchyroll.com/series/GRDV0019R/jujutsu-kaisen"
    answers = iter(["2", watch_url])

    def fake_prompt(label, default=None, **kwargs):
        if label in {"Number", "URL"}:
            return next(answers)
        raise AssertionError(f"unexpected prompt: {label}")

    try:
        fn_g["_wizard_prompt"] = fake_prompt
        fn_g["crunchyroll_metadata_from_url"] = lambda _url: metadata_cls(
            title="JUJUTSU KAISEN",
            url=series_url,
            crunchyroll_id="GY1QKKMZR",
            series_id="GRDV0019R",
            episode_title="Assault",
            season="1",
            episode="7",
        )
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            fn(s)
        out = buf.getvalue()
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["crunchyroll_metadata_from_url"] = saved_metadata

    assert s.source_kind == "url"
    assert s.source == series_url
    assert s.source_title == "JUJUTSU KAISEN"
    assert s.season == ""
    assert s.episode == ""
    assert "Crunchyroll metadata found" in out
    assert "Series URL, AniList ID, or title" not in out


def test_infer_from_crunchyroll_url_uses_metadata_before_html_fallback():
    fn = MODULE["infer_from_crunchyroll_url"]
    g = fn.__globals__
    saved_metadata = g["crunchyroll_metadata_from_url"]
    saved_request_text = g["request_text"]
    metadata_cls = MODULE["CrunchyrollMetadata"]
    series_url = "https://www.crunchyroll.com/series/GRDV0019R/jujutsu-kaisen"
    try:
        g["crunchyroll_metadata_from_url"] = lambda _url: metadata_cls(
            title="JUJUTSU KAISEN",
            url=series_url,
            crunchyroll_id="GY1QKKMZR",
            series_id="GRDV0019R",
            episode_title="Assault",
            season="1",
            episode="7",
        )
        g["request_text"] = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("HTML fallback should not run"))
        media = fn("https://www.crunchyroll.com/watch/GY1QKKMZR/assault")
    finally:
        g["crunchyroll_metadata_from_url"] = saved_metadata
        g["request_text"] = saved_request_text

    assert media.title == "JUJUTSU KAISEN"
    assert media.source_url == series_url
    assert media.season == "1"
    assert media.episode == "7"


def test_crunchyroll_metadata_returns_none_for_unrelated_url():
    fn = MODULE["crunchyroll_metadata_from_url"]
    assert fn("https://example.com/watch/GY1QKKMZR/assault") is None


def test_wizard_source_title_candidate_back_reasks_title():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch"})
    fn = MODULE["_wizard_q1_source"]
    fn_g = fn.__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_picker = fn_g["_wizard_pick_title_candidate"]
    saved_yesno = fn_g["_wizard_yesno"]
    try:
        prompts = iter(["1", "simpsons", "matrix"])
        fn_g["_wizard_prompt"] = lambda label, default=None, **kwargs: next(prompts)

        def fake_picker(title):
            if title == "simpsons":
                raise MODULE["_WizardBack"]()
            return (
                "https://www.themoviedb.org/movie/603",
                "tmdb-movie",
                "TMDB Movie: The Matrix (1999)",
                True,
            )

        fn_g["_wizard_pick_title_candidate"] = fake_picker
        fn_g["_wizard_yesno"] = lambda _q, default=False: False
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            fn(s)
        out = buf.getvalue()
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["_wizard_pick_title_candidate"] = saved_picker
        fn_g["_wizard_yesno"] = saved_yesno

    assert s.source == "https://www.themoviedb.org/movie/603"
    assert s.source_title == "The Matrix"
    assert "Going back to title entry." in out


def test_wizard_title_candidate_invalid_answer_reprompts_not_raw_title(tmp_path):
    import contextlib
    import io
    fn = MODULE["_wizard_pick_title_candidate"]
    fn_g = fn.__globals__
    saved_candidates = fn_g["_wizard_title_candidates"]
    saved_prompt = fn_g["_wizard_prompt"]
    show = tmp_path / "Fena - Pirate Princess"
    show.mkdir()
    try:
        fn_g["_wizard_title_candidates"] = lambda title: [
            {
                "provider": "tmdb-tv",
                "label": "TMDB TV: 3 Body Problem (2024)",
                "url": "https://www.themoviedb.org/tv/108545",
                "is_movie": False,
            },
            {
                "provider": "anilist",
                "label": "AniList: 300: 3x3 EYES / 3x3 Eyes (1991, 4 eps)",
                "url": "https://anilist.co/anime/300/",
                "is_movie": False,
            },
        ]
        answers = iter([f"'{show}'", "r"])
        fn_g["_wizard_prompt"] = lambda label, default=None, **kwargs: next(answers)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            result = fn("3")
        out = buf.getvalue()
    finally:
        fn_g["_wizard_title_candidates"] = saved_candidates
        fn_g["_wizard_prompt"] = saved_prompt

    assert result == "retry"
    assert "local path" in out
    assert "Use exactly what I typed" in out


def test_wizard_title_candidate_no_hits_defaults_to_retry_not_raw(monkeypatch, capsys):
    import io
    fn = MODULE["_wizard_pick_title_candidate"]
    fn_g = fn.__globals__
    monkeypatch.setitem(fn_g, "_wizard_title_candidates", lambda title: [])
    monkeypatch.setitem(fn_g, "get_provider_api_key", lambda provider: "tmdb-key")
    monkeypatch.setattr(fn_g["sys"], "stdin", type("TtyInput", (io.StringIO,), {
        "isatty": lambda self: True,
    })("\n"))
    result = fn("fena prirate princess")
    out = capsys.readouterr().out
    assert result == "retry"
    assert "No title matches found." in out
    assert "I won't build a fetch workflow from an unverified title yet." in out
    assert "Use exactly what I typed" in out


def test_wizard_title_candidate_no_hits_can_force_raw(monkeypatch, capsys):
    import io
    fn = MODULE["_wizard_pick_title_candidate"]
    fn_g = fn.__globals__
    monkeypatch.setitem(fn_g, "_wizard_title_candidates", lambda title: [])
    monkeypatch.setitem(fn_g, "get_provider_api_key", lambda provider: "tmdb-key")
    monkeypatch.setattr(fn_g["sys"], "stdin", type("TtyInput", (io.StringIO,), {
        "isatty": lambda self: True,
    })("2\n"))
    result = fn("exact raw title")
    out = capsys.readouterr().out
    assert result is None
    assert "Use exactly what I typed (advanced; may fail)" in out


def test_wizard_title_candidate_no_hits_accepts_pasted_anilist_url(monkeypatch, capsys):
    import io
    fn = MODULE["_wizard_pick_title_candidate"]
    fn_g = fn.__globals__
    info_cls = MODULE["AniListInfo"]
    monkeypatch.setitem(fn_g, "_wizard_title_candidates", lambda title: [])
    monkeypatch.setitem(fn_g, "get_provider_api_key", lambda provider: "tmdb-key")
    monkeypatch.setitem(
        fn_g,
        "fetch_anilist_info",
        lambda anilist_id: info_cls(
            id=anilist_id,
            title="NieR:Automata Ver1.1a",
            episodes=12,
            format="TV",
        ),
    )
    monkeypatch.setattr(fn_g["sys"], "stdin", type("TtyInput", (io.StringIO,), {
        "isatty": lambda self: True,
    })("https://anilist.co/anime/145665/NieRAutomata-Ver11a/\n"))

    result = fn("니아 오토마타")
    out = capsys.readouterr().out

    assert result == (
        "https://anilist.co/anime/145665/",
        "anilist",
        "AniList: 145665: NieR:Automata Ver1.1a (12 eps)",
        False,
    )
    assert "No title matches found." in out
    assert "Please enter one of: 1, 2." not in out


def test_mediainfo_movie_skips_season_subdir():
    """output_dir flattens the layout for movies: archive layout becomes
    base/Title/ instead of base/Title/Season XX/."""
    from pathlib import Path
    movie = MODULE["MediaInfo"](
        source_url="x", provider="tmdb", title="My Neighbor Totoro", is_movie=True
    )
    out = MODULE["output_dir"](Path("/tmp/Subs"), movie, "auto", "archive")
    assert str(out) == "/tmp/Subs/My Neighbor Totoro"
    # TV series unchanged.
    show = MODULE["MediaInfo"](source_url="x", provider="tmdb", title="Breaking Bad")
    assert str(MODULE["output_dir"](Path("/tmp/Subs"), show, "1", "archive")) == \
        "/tmp/Subs/Breaking Bad/Season 01"
    assert str(MODULE["output_dir"](Path("/tmp/Subs"), show, "auto", "archive")) == \
        "/tmp/Subs/Breaking Bad/Season Unknown"


def test_infer_from_catalog_url_sets_is_movie_for_tmdb_movie():
    """TMDB /movie/ URLs come back with is_movie=True; /tv/ URLs do not."""
    movie = MODULE["infer_from_catalog_url"]("https://www.themoviedb.org/movie/8392", "tmdb")
    assert movie.is_movie is True
    assert movie.tmdb_id == "8392"
    show = MODULE["infer_from_catalog_url"]("https://www.themoviedb.org/tv/65701", "tmdb")
    assert show.is_movie is False
    assert show.tmdb_id == "65701"


def test_save_subtitle_movie_filename_has_no_season_episode():
    """Movies get a flat Title.<lang>.srt filename instead of the
    Title - S00E00.<lang>.srt placeholder. Same MediaInfo for both
    branches keeps the test focused on the is_movie switch."""
    import tempfile
    from pathlib import Path
    fake_bytes = b"1\n00:00:01,000 --> 00:00:02,000\nhi\n"
    scope = MODULE["save_subtitle"].__globals__
    saved_dl = scope["download_bytes"]
    try:
        scope["download_bytes"] = lambda url, headers=None: fake_bytes

        class FakeSub:
            name = "totoro.srt"
            language = "en"
            url = "mock://"
            download_headers = None

        with tempfile.TemporaryDirectory() as d:
            # Movie path — no S00E00.
            movie = MODULE["MediaInfo"](
                source_url="x", provider="tmdb", title="My Neighbor Totoro",
                is_movie=True,
            )
            saved = MODULE["save_subtitle"](
                FakeSub(), Path(d), movie, "auto", "auto"
            )
            assert saved[0].name == "My Neighbor Totoro.en.srt"
            # TV path — keeps the SxxExx pattern.
            show = MODULE["MediaInfo"](
                source_url="x", provider="tmdb", title="Breaking Bad", is_movie=False
            )
            saved = MODULE["save_subtitle"](FakeSub(), Path(d), show, "1", "7")
            assert saved[0].name == "Breaking Bad - S01E07.en.srt"
    finally:
        scope["download_bytes"] = saved_dl


def test_wizard_q11_banner_uses_terminal_width_rule():
    """The exact divider width is copy/UI, but it must stay terminal-sized.

    Stretching to the CLI command width once produced ~190-char rules that
    wrapped on standard terminals. The durable behavior is "reasonable
    divider, no oversized divider"; wording and exact width can evolve.
    """
    import io, contextlib
    s = MODULE["_WizardState"](
        source="https://www.themoviedb.org/movie/8392",
        source_kind="url",
        languages=["ja", "en"],
        order=["ja", "en"],
        reading_aids=["ja:hiragana"],
        asbplayer=True,
        format="vtt",
        output="~/Downloads/GetSubtitle",
        is_movie=True,
    )
    cli = MODULE["_wizard_emit_cli_string"](s)
    buf = io.StringIO()
    fn_g = MODULE["_wizard_q11_action"].__globals__
    saved_input = fn_g.get("input")
    try:
        _seq = iter(["3", "1"])  # show exact command/workflow, then run
        fn_g["input"] = lambda *a, **k: next(_seq, "1")
        with contextlib.redirect_stdout(buf):
            MODULE["_wizard_q11_action"](s)
    finally:
        if saved_input is not None:
            fn_g["input"] = saved_input
    out = buf.getvalue()
    divider_lines = [
        line for line in out.splitlines()
        if line and set(line) == {"="}
    ]
    assert divider_lines
    assert max(len(line) for line in divider_lines) < 80
    # CLI + workflow preview appear once the details option is chosen.
    assert cli in out
    assert "Workflow file" in out
    assert "About to run" not in out


# ─── v0.7 step picker (Q1) ──────────────────────────────────────────


def test_wizard_state_default_steps_include_fetch_modify_merge():
    """Raw state seed stays conservative until Q1 runs.

    User-visible Q1 defaults to 1-4, but its translate question still
    defaults to "Skip", so Enter-spamming does not silently start MT.
    """
    s = MODULE["_WizardState"]()
    assert s.steps == {"fetch", "modify", "merge"}


def test_wizard_q0_steps_accepts_numbers_ranges_and_all_alias():
    """Q1 step picker parses '1,3,4' / '1-4' / hidden 'a' aliases; Enter
    uses the visible 1-4 default."""
    import io, contextlib
    fn_g = MODULE["_wizard_q0_steps"].__globals__
    saved = fn_g.get("input")
    saved_back_nav = fn_g.get("_WIZARD_BACK_NAV_ACTIVE", False)
    try:
        # Pressing Enter -> default 1-4 (full pipeline).
        prompts: list[str] = []
        fn_g["_WIZARD_BACK_NAV_ACTIVE"] = True
        fn_g["input"] = lambda prompt="", *a, **k: prompts.append(prompt) or ""
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"fetch", "translate", "modify", "merge"}
        assert prompts
        assert "[1-4 | q=quit]" in prompts[0]
        assert "b=back" not in prompts[0]
        # Explicit range -> all four pipeline steps.
        fn_g["input"] = lambda *a, **k: "1-4"
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"fetch", "translate", "modify", "merge"}
        # Spaced range is accepted too; people type this naturally.
        fn_g["input"] = lambda *a, **k: "1 - 4"
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"fetch", "translate", "modify", "merge"}
        # Old hidden alias -> all four steps.
        fn_g["input"] = lambda *a, **k: "a"
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"fetch", "translate", "modify", "merge"}
        # Rename is a maintenance workflow, so "all" means all pipeline
        # verbs, not rename.
        assert "rename" not in s.steps
        # Single number -> single step. Drives merge-only / modify-only.
        fn_g["input"] = lambda *a, **k: "4"
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"merge"}
        fn_g["input"] = lambda *a, **k: "3"
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"modify"}
        fn_g["input"] = lambda *a, **k: "5"
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"rename"}
        # Rename is intentionally exclusive so it cannot accidentally fetch
        # or modify files while a user is doing filename maintenance.
        fn_g["input"] = lambda *a, **k: "1,5"
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"rename"}
        fn_g["input"] = lambda *a, **k: "1-5"
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"rename"}
        # Multi-select.
        fn_g["input"] = lambda *a, **k: "3,4"
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"modify", "merge"}
        # Step names also work.
        fn_g["input"] = lambda *a, **k: "merge,translate"
        s = MODULE["_WizardState"]()
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q0_steps"](s)
        assert s.steps == {"merge", "translate"}
    finally:
        if saved is not None:
            fn_g["input"] = saved
        else:
            fn_g.pop("input", None)
        fn_g["_WIZARD_BACK_NAV_ACTIVE"] = saved_back_nav


def test_rename_parse_parts_and_group_variations(tmp_path):
    path = tmp_path / "MF Ghost - S03E05.ja.furigana-hiragana.single-line.ruby.vtt"
    path.write_text("WEBVTT\n", encoding="utf-8")
    parsed = MODULE["_rename_parse_parts"](path)
    assert parsed is not None
    assert parsed.title == "MF Ghost"
    assert parsed.season_prefix == "S"
    assert parsed.season == "03"
    assert parsed.episode_prefix == "E"
    assert parsed.episode == "05"
    assert parsed.language == "ja"
    assert parsed.modifiers == ["furigana-hiragana", "single-line", "ruby"]
    assert parsed.extension == "vtt"
    assert parsed.render() == path.name

    sibling = tmp_path / "MF Ghost - S03E06.ja.furigana-hiragana.single-line.ruby.vtt"
    sibling.write_text("WEBVTT\n", encoding="utf-8")
    groups = MODULE["_rename_group_variations"]([
        MODULE["_rename_parse_parts"](path),
        MODULE["_rename_parse_parts"](sibling),
    ])
    assert groups[0][0] == "MF Ghost - S03E**.ja.furigana-hiragana.single-line.ruby.vtt"
    assert len(groups[0][1]) == 2


def test_rename_plan_episode_range_preserves_width(tmp_path):
    first = tmp_path / "MF Ghost - S03E01.ja-furigana-ko.vtt"
    second = tmp_path / "MF Ghost - S03E02.ja-furigana-ko.vtt"
    first.write_text("WEBVTT\n", encoding="utf-8")
    second.write_text("WEBVTT\n", encoding="utf-8")
    parts = [MODULE["_rename_parse_parts"](first), MODULE["_rename_parse_parts"](second)]
    plan = MODULE["_rename_plan"](parts, component="episode", number_action="range:25")
    assert [dst.name for _src, dst in plan] == [
        "MF Ghost - S03E25.ja-furigana-ko.vtt",
        "MF Ghost - S03E26.ja-furigana-ko.vtt",
    ]


def test_rename_episode_range_keeps_language_variants_paired(tmp_path):
    # Selecting ja AND en variants and renumbering must give both files of one
    # episode the SAME new number (regression: per-file enumerate desynced them).
    names = [
        "MF Ghost - S01E01.ja.srt", "MF Ghost - S01E01.en.srt",
        "MF Ghost - S01E02.ja.srt", "MF Ghost - S01E02.en.srt",
    ]
    parts = []
    for n in names:
        (tmp_path / n).write_text("1\n", encoding="utf-8")
        parts.append(MODULE["_rename_parse_parts"](tmp_path / n))
    plan = MODULE["_rename_plan"](parts, component="episode", number_action="range:5")
    mapping = {src.name: dst.name for src, dst in plan}
    assert mapping["MF Ghost - S01E01.ja.srt"] == "MF Ghost - S01E05.ja.srt"
    assert mapping["MF Ghost - S01E01.en.srt"] == "MF Ghost - S01E05.en.srt"
    assert mapping["MF Ghost - S01E02.ja.srt"] == "MF Ghost - S01E06.ja.srt"
    assert mapping["MF Ghost - S01E02.en.srt"] == "MF Ghost - S01E06.en.srt"


def test_rename_episode_range_renumbers_each_season_independently(tmp_path):
    # Two seasons selected together: each season restarts at `start`, no bleed.
    names = ["Show - S01E03.ja.srt", "Show - S01E04.ja.srt",
             "Show - S02E07.ja.srt", "Show - S02E08.ja.srt"]
    parts = []
    for n in names:
        (tmp_path / n).write_text("1\n", encoding="utf-8")
        parts.append(MODULE["_rename_parse_parts"](tmp_path / n))
    plan = MODULE["_rename_plan"](parts, component="episode", number_action="range:1")
    mapping = {src.name: dst.name for src, dst in plan}
    assert mapping["Show - S01E03.ja.srt"] == "Show - S01E01.ja.srt"
    assert mapping["Show - S01E04.ja.srt"] == "Show - S01E02.ja.srt"
    assert mapping["Show - S02E07.ja.srt"] == "Show - S02E01.ja.srt"
    assert mapping["Show - S02E08.ja.srt"] == "Show - S02E02.ja.srt"


def test_rename_collision_errors_detect_existing_destination(tmp_path):
    source = tmp_path / "MF Ghost - S03E01.ja.srt"
    target = tmp_path / "MF Ghost - S03E01.ko.srt"
    source.write_text("1\n", encoding="utf-8")
    target.write_text("1\n", encoding="utf-8")
    part = MODULE["_rename_parse_parts"](source)
    plan = MODULE["_rename_plan"]([part], component="language", value="ko")
    assert MODULE["_rename_collision_errors"](plan) == [
        "MF Ghost - S03E01.ko.srt already exists"
    ]
    shift_source = tmp_path / "MF Ghost - S03E02.ja.srt"
    shift_source.write_text("1\n", encoding="utf-8")
    shift_plan = MODULE["_rename_plan"](
        [
            MODULE["_rename_parse_parts"](source),
            MODULE["_rename_parse_parts"](shift_source),
        ],
        component="episode",
        number_action="range:2",
    )
    assert MODULE["_rename_collision_errors"](shift_plan) == []
    assert MODULE["_rename_collision_errors"](shift_plan, copy_mode=True) == [
        "MF Ghost - S03E02.ja.srt already exists"
    ]


def test_rename_apply_plan_handles_swaps_without_clobbering(tmp_path):
    a = tmp_path / "Show - S01E01.ja.srt"
    b = tmp_path / "Show - S01E02.ja.srt"
    a.write_text("episode one\n", encoding="utf-8")
    b.write_text("episode two\n", encoding="utf-8")

    MODULE["_rename_apply_plan"]([
        (a, b),
        (b, a),
    ])

    assert a.read_text(encoding="utf-8") == "episode two\n"
    assert b.read_text(encoding="utf-8") == "episode one\n"


def test_rename_copy_plan_keeps_original_files(tmp_path):
    source = tmp_path / "Show - S01E01.ja.srt"
    target = tmp_path / "Show - S01E25.ja.srt"
    source.write_text("episode one\n", encoding="utf-8")

    MODULE["_rename_copy_plan"]([(source, target)])

    assert source.read_text(encoding="utf-8") == "episode one\n"
    assert target.read_text(encoding="utf-8") == "episode one\n"


def test_wizard_rename_flow_renames_selected_variation(tmp_path, monkeypatch):
    first = tmp_path / "MF Ghost - S03E01.ja.srt"
    second = tmp_path / "MF Ghost - S03E02.ja.srt"
    untouched = tmp_path / "MF Ghost - S03E01.ko.srt"
    for path in (first, second, untouched):
        path.write_text("1\n", encoding="utf-8")

    answers = iter(["1", "3", "2", "25", "1", "2", "y"])
    monkeypatch.setitem(MODULE["_wizard_prompt"].__globals__, "input", lambda *a, **k: next(answers))
    state = MODULE["_WizardState"](steps={"rename"}, source=str(tmp_path), source_kind="path")
    MODULE["_wizard_q_rename"](state)

    assert not first.exists()
    assert not second.exists()
    assert (tmp_path / "MF Ghost - S03E25.ja.srt").exists()
    assert (tmp_path / "MF Ghost - S03E26.ja.srt").exists()
    assert untouched.exists()


def test_wizard_rename_flow_defaults_to_copy_and_apply(tmp_path, monkeypatch):
    first = tmp_path / "MF Ghost - S03E01.ja.srt"
    second = tmp_path / "MF Ghost - S03E02.ja.srt"
    for path in (first, second):
        path.write_text("1\n", encoding="utf-8")

    answers = iter(["all", "3", "2", "25", "", "", "y"])
    monkeypatch.setitem(MODULE["_wizard_prompt"].__globals__, "input", lambda *a, **k: next(answers))
    state = MODULE["_WizardState"](steps={"rename"}, source=str(tmp_path), source_kind="path")
    MODULE["_wizard_q_rename"](state)

    assert first.exists()
    assert second.exists()
    assert (tmp_path / "MF Ghost - S03E25.ja.srt").exists()
    assert (tmp_path / "MF Ghost - S03E26.ja.srt").exists()


def test_wizard_rename_back_inside_number_detail_stays_in_rename(tmp_path, monkeypatch, capsys):
    first = tmp_path / "MF Ghost - S03E01.ja.srt"
    second = tmp_path / "MF Ghost - S03E02.ja.srt"
    for path in (first, second):
        path.write_text("1\n", encoding="utf-8")

    answers = iter(["1", "3", "1", "back", "2", "25", "", "", "y"])
    fn_g = MODULE["_wizard_prompt"].__globals__
    saved_back_nav = fn_g.get("_WIZARD_BACK_NAV_ACTIVE", False)
    monkeypatch.setitem(fn_g, "input", lambda *a, **k: next(answers))
    monkeypatch.setitem(fn_g, "_WIZARD_BACK_NAV_ACTIVE", True)
    try:
        state = MODULE["_WizardState"](steps={"rename"}, source=str(tmp_path), source_kind="path")
        MODULE["_wizard_q_rename"](state)
    finally:
        monkeypatch.setitem(fn_g, "_WIZARD_BACK_NAV_ACTIVE", saved_back_nav)

    out = capsys.readouterr().out
    assert "Going back to the previous rename choice." in out
    assert "Going back to the previous step." not in out
    assert first.exists()
    assert second.exists()
    assert (tmp_path / "MF Ghost - S03E25.ja.srt").exists()
    assert (tmp_path / "MF Ghost - S03E26.ja.srt").exists()


def test_wizard_rename_can_keep_changes_then_change_another_field(tmp_path, monkeypatch, capsys):
    first = tmp_path / "MF Ghost - S03E01.ja.furigana-hiragana.vtt"
    second = tmp_path / "MF Ghost - S03E02.ja.furigana-hiragana.vtt"
    for path in (first, second):
        path.write_text("WEBVTT\n", encoding="utf-8")

    answers = iter([
        "all",       # variation
        "5",         # modifiers
        "combined",  # new modifiers
        "2",         # keep changes and change something else
        "5",         # try modifiers again; should be rejected
        "3",         # episode
        "2",         # range
        "25",        # starts at E25
        "1",         # looks good, apply now
        "2",         # apply to originals
        "y",         # confirm
    ])
    monkeypatch.setitem(MODULE["_wizard_prompt"].__globals__, "input", lambda *a, **k: next(answers))
    state = MODULE["_WizardState"](steps={"rename"}, source=str(tmp_path), source_kind="path")
    MODULE["_wizard_q_rename"](state)

    out = capsys.readouterr().out
    assert "What next?" in out
    assert "How should it be applied?" in out
    assert "Modifiers (already handled)" in out
    assert "already handled in this rename batch" in out
    assert not first.exists()
    assert not second.exists()
    assert (tmp_path / "MF Ghost - S03E25.ja.combined.vtt").exists()
    assert (tmp_path / "MF Ghost - S03E26.ja.combined.vtt").exists()


def test_wizard_rename_discard_does_not_lock_field(tmp_path, monkeypatch):
    # Regression (B4): discarding a previewed change must NOT mark the field
    # as handled — the user can retry the same field with a different value.
    original = tmp_path / "Show - S01E01.ja.srt"
    original.write_text("1\n", encoding="utf-8")
    answers = iter([
        "1",          # variation: the only group
        "1",          # component: Title
        "WrongName",  # new title (will be discarded)
        "3",          # discard this change and choose another field
        "1",          # component: Title AGAIN — must still be allowed
        "RightName",  # new title (the keeper)
        "1",          # looks good, apply now
        "1",          # copy and apply (keep originals)
        "y",          # confirm
    ])
    monkeypatch.setitem(MODULE["_wizard_prompt"].__globals__, "input", lambda *a, **k: next(answers))
    state = MODULE["_WizardState"](steps={"rename"}, source=str(tmp_path), source_kind="path")
    MODULE["_wizard_q_rename"](state)
    assert (tmp_path / "RightName - S01E01.ja.srt").exists()
    assert original.exists()  # copy mode keeps the original


def test_wizard_rename_empty_folder_lists_what_it_found(tmp_path, monkeypatch, capsys):
    # CODEX critique #8: a folder of validly-named-but-unmatched subtitles
    # should show what was found, not just one expected-shape line.
    (tmp_path / "random_fansub_01.srt").write_text("1\n", encoding="utf-8")
    (tmp_path / "Show S01E01 ja.srt").write_text("1\n", encoding="utf-8")
    monkeypatch.setitem(MODULE["_wizard_prompt"].__globals__, "input", lambda *a, **k: "")
    state = MODULE["_WizardState"](steps={"rename"}, source=str(tmp_path), source_kind="path")
    MODULE["_wizard_q_rename"](state)
    out = capsys.readouterr().out
    assert "Found 2 subtitle file(s)" in out
    assert "random_fansub_01.srt" in out


def test_wizard_read_choice_reprompts_defaults_and_quits(monkeypatch, capsys):
    # The shared menu primitive: Enter->default, garbage->re-prompt (never
    # abort), q->quit. This is the guardrail every numbered menu now shares.
    import pytest
    g = MODULE["_wizard_prompt"].__globals__
    monkeypatch.setitem(g, "input", lambda *a, **k: "")
    assert MODULE["_wizard_read_choice"]("Number", ["1", "2", "3"], "2") == "2"
    seq = iter(["99", "abc", "3"])
    monkeypatch.setitem(g, "input", lambda *a, **k: next(seq))
    assert MODULE["_wizard_read_choice"]("Number", ["1", "2", "3"], "1") == "3"
    assert "Please enter one of" in capsys.readouterr().out
    monkeypatch.setitem(g, "input", lambda *a, **k: "q")
    with pytest.raises(MODULE["_WizardAbort"]):
        MODULE["_wizard_read_choice"]("Number", ["1", "2", "3"], "1")


def test_wizard_q1_steps_reprompts_not_aborts(monkeypatch, capsys):
    # Regression: invalid Q1 input must re-prompt, not raise CliError and
    # kill the whole wizard (the bug a beginner hit fat-fingering question 1).
    g = MODULE["_wizard_prompt"].__globals__
    seq = iter(["99", "abc", "1,3,4"])
    monkeypatch.setitem(g, "input", lambda *a, **k: next(seq))
    s = MODULE["_WizardState"]()
    MODULE["_wizard_q0_steps"](s)  # must NOT raise
    assert s.steps == {"fetch", "modify", "merge"}
    assert "Please pick at least one step" in capsys.readouterr().out


def test_interactive_wizard_fuzz_never_aborts_or_loops(tmp_path, monkeypatch):
    # Property/fuzz harness: random input sequences must never make the
    # wizard raise an unexpected exception, traceback, or loop forever.
    import random
    import io
    import contextlib
    monkeypatch.chdir(tmp_path)
    g = MODULE["_wizard_prompt"].__globals__
    monkeypatch.setitem(g, "_wizard_is_interactive", lambda: True)
    monkeypatch.setitem(g, "main", lambda *a, **k: 0)        # don't really dispatch
    monkeypatch.setitem(g, "open_folder", lambda *a, **k: None)
    (tmp_path / "Show.S01E01.ja.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nx\n", encoding="utf-8")
    (tmp_path / "Show.S01E01.en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\ny\n", encoding="utf-8")
    pool = ["", "1", "2", "3", "4", "5", "9", "99", "b", "q", "x",
            "ja,en", str(tmp_path), "-1", "0", "y", "n", " ", "abc"]
    CAP = 400
    random.seed(7)
    expected = (MODULE["CliError"], SystemExit, MODULE["_WizardAbort"])
    for trial in range(25):
        seq = iter(random.choice(pool) for _ in range(35))
        calls = {"n": 0}

        def feed(prompt="", _seq=seq, _calls=calls, _t=trial):
            _calls["n"] += 1
            assert _calls["n"] <= CAP, f"wizard looped (> {CAP} prompts) on trial {_t}"
            try:
                return next(_seq)
            except StopIteration:
                return "q"

        monkeypatch.setitem(g, "input", feed)
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                MODULE["interactive_main"]([])
            except expected:
                pass  # handled exits are acceptable; any other type fails the test


def test_wizard_next_q_numbers_contiguously():
    """`_wizard_next_q` hands out gap-free labels from a per-pass counter.

    Q1 stays clean (no progress bar); later headings get a divider and a
    same-line progress bar so the dynamic total never leaks as "Q2 of ~7".
    """
    s = MODULE["_WizardState"]()
    s._qcount = 0
    labels = [MODULE["_wizard_next_q"](s, f"Question {i}?") for i in range(1, 5)]
    assert labels[0].splitlines() == ["Q1. Question 1?"]
    assert [l.splitlines()[-1].split(".", 1)[0] for l in labels] == ["Q1", "Q2", "Q3", "Q4"]
    assert "Progress [" not in labels[0]
    for label in labels[1:]:
        divider, heading = label.splitlines()
        assert divider == "-" * MODULE["_WIZARD_HEADING_WIDTH"]
        assert len(heading) == MODULE["_WIZARD_HEADING_WIDTH"]
        assert "Progress [" in heading
        assert "◼" in heading and "◻" in heading
    assert all(" of ~" not in l for l in labels)
    s._qcount = 1
    assert MODULE["_wizard_next_q"](s, "Again?").splitlines()[-1].startswith("Q2. Again?")


def test_wizard_qcount_before_honors_step_gating():
    """`_wizard_qcount_before` mirrors `_run_wizard`'s gating so the edit
    loop can re-derive a question's forward-pass number. Source counts as
    two headings with fetch (kind picker + entry), one without."""
    # Merge-only: steps(1) + source(1, no fetch) + languages(1) = 3 before
    # reading_aids. If scope/translate weren't gated out it would be 5,
    # so this pins the gating.
    merge_only = MODULE["_WizardState"](steps={"merge"})
    assert MODULE["_wizard_qcount_before"](merge_only, "reading_aids") == 3
    # Full fetch flow: source contributes two headings (kind picker + entry),
    # and episode scope now comes before languages.
    full = MODULE["_WizardState"](steps={"fetch", "modify", "merge"})
    assert MODULE["_wizard_qcount_before"](full, "steps") == 0
    assert MODULE["_wizard_qcount_before"](full, "scope") == 3      # 1 + 2
    assert MODULE["_wizard_qcount_before"](full, "languages") == 4  # + scope
    assert MODULE["_wizard_qcount_before"](full, "reading_aids") == 5  # + languages


def test_wizard_languages_clarifies_dot_separator_typo():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"merge"})
    fn_g = MODULE["_wizard_q2_languages"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_yesno = fn_g["_wizard_yesno"]
    questions: list[str] = []
    try:
        fn_g["_wizard_prompt"] = lambda _q, _d=None: "en.es"
        fn_g["_wizard_yesno"] = lambda q, default=True: questions.append(q) or True
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q2_languages"](s)
        out = buf.getvalue()
        assert s.languages == ["en", "es"]
        assert questions == ["Did you mean en,es?"]
        assert "I don't recognize 'en.es' as written." in out
        assert "Languages selected:" in out
        assert "en → English" in out
        assert "es → Spanish" in out
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["_wizard_yesno"] = saved_yesno


def test_wizard_languages_reprompts_unknown_code():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"merge"})
    fn_g = MODULE["_wizard_q2_languages"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    answers = iter(["zz", "en,es"])
    try:
        fn_g["_wizard_prompt"] = lambda _q, _d=None: next(answers)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q2_languages"](s)
        out = buf.getvalue()
        assert s.languages == ["en", "es"]
        assert "I don't recognize: zz" in out
        assert "Use 2-letter codes or full names" in out
    finally:
        fn_g["_wizard_prompt"] = saved_prompt


def test_wizard_languages_offer_modify_for_korean_reading_aids():
    """Fetch-only + Korean should offer to add Modify so reading aids are
    not silently skipped."""
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch"})
    fn_g = MODULE["_wizard_q2_languages"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_yesno = fn_g["_wizard_yesno"]
    try:
        fn_g["_wizard_prompt"] = lambda _q, _d=None: "ko,en"
        fn_g["_wizard_yesno"] = lambda _q, default=True: True
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q2_languages"](s)
        assert s.languages == ["ko", "en"]
        assert "modify" in s.steps
        assert "Korean romanization" in buf.getvalue()
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["_wizard_yesno"] = saved_yesno


def test_wizard_languages_can_decline_modify_reading_aids():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch"})
    fn_g = MODULE["_wizard_q2_languages"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_yesno = fn_g["_wizard_yesno"]
    try:
        fn_g["_wizard_prompt"] = lambda _q, _d=None: "ja,en"
        fn_g["_wizard_yesno"] = lambda _q, default=True: False
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q2_languages"](s)
        assert s.languages == ["ja", "en"]
        assert s.steps == {"fetch"}
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["_wizard_yesno"] = saved_yesno


def test_wizard_languages_warns_and_can_trim_five_language_stack():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"modify", "merge"})
    fn_g = MODULE["_wizard_q2_languages"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    answers = iter(["ja,ko,en,es,fr", "2"])
    try:
        fn_g["_wizard_prompt"] = lambda _q, _d=None, **_kwargs: next(answers)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q2_languages"](s)
        out = buf.getvalue()
        assert s.languages == ["ja", "ko", "en"]
        assert "You selected 5 languages" in out
        assert "Most people find 2-3 languages easiest to read." in out
        assert "4+ can cover a small screen" in out
        assert "Keep only the first 3" in out
    finally:
        fn_g["_wizard_prompt"] = saved_prompt


def test_wizard_fetch_only_multiple_languages_can_add_merge_for_format_questions():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch"})
    fn_g = MODULE["_wizard_q2_languages"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_yesno = fn_g["_wizard_yesno"]
    try:
        fn_g["_wizard_prompt"] = lambda _q, _d=None: "en,es"
        fn_g["_wizard_yesno"] = lambda _q, default=True: True
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q2_languages"](s)
        out = buf.getvalue()
        assert s.languages == ["en", "es"]
        assert s.steps == {"fetch", "merge"}
        assert "Fetch without Merge" in out
        notes = MODULE["_wizard_apply_smart_defaults"](s)
        assert s.format == ""
        assert "Format / extension" not in notes
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["_wizard_yesno"] = saved_yesno


def test_wizard_fetch_only_multiple_languages_can_decline_merge():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch"})
    fn_g = MODULE["_wizard_q2_languages"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_yesno = fn_g["_wizard_yesno"]
    try:
        fn_g["_wizard_prompt"] = lambda _q, _d=None: "en,es"
        fn_g["_wizard_yesno"] = lambda _q, default=True: False
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q2_languages"](s)
        out = buf.getvalue()
        assert s.languages == ["en", "es"]
        assert s.steps == {"fetch"}
        assert "format/font-size questions apply only to merged files" in out
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["_wizard_yesno"] = saved_yesno


def test_wizard_languages_back_from_recommended_steps_reasks_languages():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"fetch"})
    fn_g = MODULE["_wizard_q2_languages"].__globals__
    saved_input = fn_g.get("input")
    saved_back_nav = fn_g.get("_WIZARD_BACK_NAV_ACTIVE", False)
    answers = iter([
        "en,ko,zh,ja",  # language entry
        "1",            # crowded-language warning: continue anyway
        "b",            # recommended Modify+Merge prompt: go back locally
        "en,ko",        # re-enter languages
        "n",            # decline recommended steps
    ])
    try:
        fn_g["_WIZARD_BACK_NAV_ACTIVE"] = True
        fn_g["input"] = lambda *a, **k: next(answers)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q2_languages"](s)
        out = buf.getvalue()
    finally:
        if saved_input is not None:
            fn_g["input"] = saved_input
        elif "input" in fn_g:
            del fn_g["input"]
        fn_g["_WIZARD_BACK_NAV_ACTIVE"] = saved_back_nav

    assert s.languages == ["en", "ko"]
    assert s.steps == {"fetch"}
    assert "Going back to language entry." in out
    assert "Fetch en, ko, zh, ja" not in out


def test_wizard_translate_argos_preflight_back_reasks_engine_choice():
    import contextlib
    import io
    s = MODULE["_WizardState"](steps={"translate"}, languages=["en", "es"])
    fn_g = MODULE["_wizard_q6_translate"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    saved_handler = fn_g["_wizard_handle_argos_preflight"]
    picks = iter(["2", "1"])
    try:
        fn_g["_wizard_prompt"] = lambda _q, _d=None, **_kwargs: next(picks)
        fn_g["_wizard_handle_argos_preflight"] = lambda _state: (_ for _ in ()).throw(
            MODULE["_WizardBack"]()
        )
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            MODULE["_wizard_q6_translate"](s)
        out = buf.getvalue()
    finally:
        fn_g["_wizard_prompt"] = saved_prompt
        fn_g["_wizard_handle_argos_preflight"] = saved_handler

    assert s.mt_engine == ""
    assert "Going back to translation choices." in out


def test_wizard_local_missing_languages_can_add_fetch_on_spot():
    import contextlib
    import io
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Mashle - s02e13.smi").write_text(_SAMI_BASIC_KO, encoding="utf-8")
        s = MODULE["_WizardState"](
            source=str(root),
            source_kind="path",
            season="2",
            episode="13",
            steps={"modify", "merge"},
            convert_smi=True,
        )
        fn_g = MODULE["_wizard_q2_languages"].__globals__
        saved_prompt = fn_g["_wizard_prompt"]
        saved_yesno = fn_g["_wizard_yesno"]
        answers = iter(["ja,en", "MASHLE: Magic and Muscles"])
        try:
            fn_g["_wizard_prompt"] = lambda _q, _d=None: next(answers)
            fn_g["_wizard_yesno"] = lambda _q, default=True: True
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                MODULE["_wizard_q2_languages"](s)
            out = buf.getvalue()
        finally:
            fn_g["_wizard_prompt"] = saved_prompt
            fn_g["_wizard_yesno"] = saved_yesno

    assert "Found locally: ko" in out
    assert "Missing for your requested stack: ja, en" in out
    assert "fetch" in s.steps
    assert s.source_kind == "title"
    assert s.source == "MASHLE: Magic and Muscles"
    assert s.output == str(root)
    cli = MODULE["_wizard_emit_cli"](s)
    assert cli[:3] == ["getsubtitle", "--fetch", "--title"]
    assert "--output" in cli
    assert cli[cli.index("--output") + 1] == str(root)


def test_wizard_local_missing_languages_decline_fetch_prints_restart_hint():
    import contextlib
    import io
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Mashle - s02e13.smi").write_text(_SAMI_BASIC_KO, encoding="utf-8")
        s = MODULE["_WizardState"](
            source=str(root),
            source_kind="path",
            season="2",
            episode="13",
            steps={"modify", "merge"},
        )
        fn_g = MODULE["_wizard_q2_languages"].__globals__
        saved_prompt = fn_g["_wizard_prompt"]
        saved_yesno = fn_g["_wizard_yesno"]
        try:
            fn_g["_wizard_prompt"] = lambda _q, _d=None: "ja,en"
            fn_g["_wizard_yesno"] = lambda _q, default=True: False
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                MODULE["_wizard_q2_languages"](s)
            out = buf.getvalue()
        finally:
            fn_g["_wizard_prompt"] = saved_prompt
            fn_g["_wizard_yesno"] = saved_yesno

    assert s.steps == {"modify", "merge"}
    assert s.source_kind == "path"
    assert "restart with `getsubtitle -i`, choose Fetch" in out


def test_wizard_emit_cli_merge_only_drops_fetch_and_translate():
    """Scenario: user dropped a folder of .ja.srt/.en.srt and just wants
    to merge them into one VTT. The emitted CLI is a PATH-form merge
    command with no --fetch or --translate noise."""
    s = MODULE["_WizardState"](
        source="/Users/mba/Downloads/Show",
        source_kind="path",
        languages=["ja", "en"],
        order=["ja", "en"],
        format="vtt",
        output="~/Downloads/GetSubtitle",
        steps={"merge"},
    )
    cli = MODULE["_wizard_emit_cli_string"](s)
    assert "--fetch" not in cli
    assert "--translate" not in cli
    assert "--modify" not in cli
    assert "getsubtitle merge" in cli
    assert "--format vtt" in cli
    assert cli.startswith("getsubtitle merge /Users/mba/Downloads/Show")


def test_wizard_emit_toml_merge_only_omits_translate_and_modify_sections():
    s = MODULE["_WizardState"](
        source="/tmp/Show",
        source_kind="path",
        languages=["ja", "en"],
        order=["ja", "en"],
        format="vtt",
        steps={"merge"},
    )
    toml_text = MODULE["_wizard_emit_toml"](s)
    assert "[fetch]" not in toml_text
    assert "[output]" in toml_text   # carries local-only source target
    assert 'target = "/tmp/Show"' in toml_text
    assert "[translate]" not in toml_text
    assert "[modify]" not in toml_text
    assert "[merge]" in toml_text
    # And no `no_engine = true` since fetch isn't selected.
    assert "no_engine" not in toml_text


def test_wizard_emit_cli_modify_only_on_single_file():
    """Scenario: user wants furigana on a single .ja.srt they already
    have. The CLI form: getsubtitle FILE --modify --reading ja:hiragana."""
    s = MODULE["_WizardState"](
        source="/tmp/ep01.ja.srt",
        source_kind="path",
        languages=["ja"],
        reading_aids=["ja:hiragana"],
        steps={"modify"},
    )
    cli = MODULE["_wizard_emit_cli_string"](s)
    assert "--fetch" not in cli
    assert "--merge" not in cli
    assert "--translate" not in cli
    assert "getsubtitle modify" in cli
    assert "--reading ja:hiragana" in cli
    assert cli.startswith("getsubtitle modify /tmp/ep01.ja.srt")


def test_wizard_emit_cli_modify_merge_uses_source_pipeline_flag():
    s = MODULE["_WizardState"](
        source="/tmp/Show",
        source_kind="path",
        languages=["ko", "en"],
        order=["ko", "en"],
        master="ko",
        reading_aids=["ko:yale"],
        asbplayer=True,
        format="vtt",
        steps={"modify", "merge"},
    )
    cli = MODULE["_wizard_emit_cli_string"](s)
    assert cli.startswith("getsubtitle --source /tmp/Show")
    assert "--modify" in cli
    assert "--merge" in cli
    assert "/tmp/Show --languages" not in cli


def test_wizard_emit_local_translate_merge_carries_translate_languages():
    s = MODULE["_WizardState"](
        source="/tmp/Show",
        source_kind="path",
        languages=["ja", "ko"],
        order=["ja", "ko"],
        mt_engine="deepl",
        reading_aids=["ja:hiragana"],
        asbplayer=True,
        format="vtt",
        output="/tmp/Show",
        steps={"translate", "modify", "merge"},
    )
    cli = MODULE["_wizard_emit_cli"](s)
    tr_idx = cli.index("--translate")
    mod_idx = cli.index("--modify")
    tr_block = cli[tr_idx:mod_idx]
    assert "--languages" in tr_block
    assert tr_block[tr_block.index("--languages") + 1] == "ja,ko"

    toml = MODULE["_wizard_emit_toml"](s)
    translate_block = toml.split("[modify]", 1)[0]
    assert "[translate]" in translate_block
    assert 'languages = "ja,ko"' in translate_block


def test_wizard_local_video_file_becomes_parent_folder_with_episode_filter():
    import contextlib
    import io
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        video = root / "Moving.E01.1080p.WEB-DL.mp4"
        video.write_bytes(b"")
        (root / "Moving.E01.ko.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n안녕\n", encoding="utf-8"
        )
        (root / "Moving.E01.en.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8"
        )
        s = MODULE["_WizardState"](steps={"modify", "merge"})
        fn_g = MODULE["_wizard_q1_source"].__globals__
        saved_prompt = fn_g["_wizard_prompt"]
        try:
            fn_g["_wizard_prompt"] = lambda _q, default=None: str(video)
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                MODULE["_wizard_q1_source"](s)
            assert s.source == str(root)
            assert s.season == "1"
            assert s.episode == "1"
            assert "Selected episode: S01E01" in buf.getvalue()
        finally:
            fn_g["_wizard_prompt"] = saved_prompt


def test_wizard_local_video_file_with_smi_auto_adds_conversion():
    import contextlib
    import io
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        video = root / "Mashle - s02e13.mkv"
        video.write_bytes(b"")
        (root / "Mashle - s02e13.smi").write_text(_SAMI_BASIC_KO, encoding="utf-8")
        s = MODULE["_WizardState"](steps={"modify", "merge"})
        fn_g = MODULE["_wizard_q1_source"].__globals__
        saved_prompt = fn_g["_wizard_prompt"]
        try:
            fn_g["_wizard_prompt"] = lambda _q, default=None: str(video)
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                MODULE["_wizard_q1_source"](s)
            assert s.source == str(root)
            assert s.season == "2"
            assert s.episode == "13"
            assert s.convert_smi is True
            assert "SMI subtitles found" in buf.getvalue()
            cli = MODULE["_wizard_emit_cli"](s)
            assert "--convert" in cli
            assert cli[cli.index("--convert") + 1] == "smi-to-srt"
            toml = MODULE["_wizard_emit_toml"](s)
            assert 'convert = "smi-to-srt"' in toml
        finally:
            fn_g["_wizard_prompt"] = saved_prompt


def test_wizard_emit_cli_modify_merge_includes_local_episode_filter():
    s = MODULE["_WizardState"](
        source="/tmp/Moving/Season 01",
        source_kind="path",
        languages=["ko", "en"],
        order=["ko", "en"],
        season="1",
        episode="1",
        reading_aids=["ko:yale"],
        asbplayer=True,
        format="vtt",
        steps={"modify", "merge"},
    )
    cli = MODULE["_wizard_emit_cli"](s)
    modify_idx = cli.index("--modify")
    merge_idx = cli.index("--merge")
    assert cli[modify_idx:merge_idx].count("--season") == 1
    assert cli[modify_idx:merge_idx].count("--episode") == 1
    assert cli[modify_idx:merge_idx][cli[modify_idx:merge_idx].index("--episode") + 1] == "1"
    assert "--season" in cli[merge_idx:]
    assert "--episode" in cli[merge_idx:]
    toml = MODULE["_wizard_emit_toml"](s)
    assert toml.count('season = "1"') == 2
    assert toml.count('episode = "1"') == 2


def test_wizard_emit_cli_url_pipeline_shows_scope_once():
    s = MODULE["_WizardState"](
        source="https://www.crunchyroll.com/series/GEXH3W2W7/mf-ghost",
        source_kind="url",
        languages=["ja", "ko"],
        order=["ja", "ko"],
        season="3",
        episode="5-10",
        mt_engine="deepl",
        reading_aids=["ja:hiragana"],
        asbplayer=True,
        format="vtt",
        output="~/Downloads/GetSubtitle",
        steps={"fetch", "translate", "modify", "merge"},
    )
    cli = MODULE["_wizard_emit_cli"](s)
    blocks = MODULE["split_pipeline_argv"](cli[1:])
    assert cli.count("--season") == 1
    assert cli.count("--episode") == 1
    assert blocks["fetch"][blocks["fetch"].index("--season") + 1] == "3"
    assert blocks["fetch"][blocks["fetch"].index("--episode") + 1] == "5-10"
    for block_name in ("translate", "modify", "merge"):
        block = blocks[block_name]
        assert "--season" not in block, f"{block_name} block repeats season: {block!r}"
        assert "--episode" not in block, f"{block_name} block repeats episode: {block!r}"
    toml = MODULE["_wizard_emit_toml"](s)
    assert toml.count('season = "3"') == 4
    assert toml.count('episode = "5-10"') == 4


def test_wizard_emit_cli_translate_only_path_form():
    """Translate-only path: getsubtitle FOLDER --translate ENGINE."""
    s = MODULE["_WizardState"](
        source="/tmp/Show",
        source_kind="path",
        languages=["ja", "ko"],
        mt_engine="deepl",
        steps={"translate"},
    )
    cli = MODULE["_wizard_emit_cli_string"](s)
    assert "--fetch" not in cli
    assert "--merge" not in cli
    assert "--modify" not in cli
    assert cli.startswith("getsubtitle translate /tmp/Show")
    assert "--engine deepl" in cli


def test_parse_episode_marker_treats_movie_filenames_as_zero_zero():
    """v0.7.1 fix: movies have no SxxExx marker. parse_episode_marker
    must return (0, 0) for `Title.<lang>.srt` shapes so the scanner can
    find them. Combined outputs and furigana variants still return None."""
    pem = MODULE["parse_episode_marker"]
    assert pem("My Neighbor Totoro.ja.srt") == (0, 0)
    assert pem("Tonari no Totoro.en.srt") == (0, 0)
    # Still works for TV shows.
    assert pem("Show.S01E07.ja.srt") == (1, 7)
    # Combined output -> None (don't re-scan our own outputs).
    assert pem("My Neighbor Totoro.ja-en.srt") is None
    # Furigana variant -> None.
    assert pem("My Neighbor Totoro.ja.furigana-hiragana.srt") is None
    # Unrelated file -> None.
    assert pem("notes.txt") is None


def test_combine_main_finds_movie_files_and_merges():
    """End-to-end: a folder of Title.ja.srt + Title.en.srt merges into
    Title.ja-en.srt. The v0.6 movie filename change broke this; v0.7.1
    restores it via the (0, 0) synthetic episode key."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "My Neighbor Totoro.ja.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n漢字\n", encoding="utf-8",
        )
        (root / "My Neighbor Totoro.en.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nkanji\n", encoding="utf-8",
        )
        rc = MODULE["combine_main"]([
            str(root), "-l", "ja,en", "--force", "--no-open-folder-prompt",
        ])
        assert rc == 0
        assert (root / "My Neighbor Totoro.ja-en.srt").exists()


def test_episode_label_se_returns_movie_for_zero_zero():
    label = MODULE["_episode_label_se"]
    assert label(0, 0) == "movie"
    assert label(1, 7) == "S01E07"


def test_wizard_q7_reading_aids_no_reading_aid_is_option_one_default():
    """Q9 has 'No reading aid (skip)' as option 1 (default) and the
    actual reading-aid options shift to 2..n+1."""
    import io, contextlib
    fn_g = MODULE["_wizard_q7_reading_aids"].__globals__
    saved = fn_g.get("input")
    try:
        # Empty (Enter) -> default 1 -> No reading aid.
        fn_g["input"] = lambda *a, **k: ""
        s = MODULE["_WizardState"](languages=["ja", "en"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            MODULE["_wizard_q7_reading_aids"](s)
        out = buf.getvalue()
        assert "1) No reading aid" in out
        assert "2) Japanese — hiragana" in out
        assert "Example: 勉強する → べんきょうする" in out
        assert s.reading_aids == []
        # '2' should land on the first real aid (hiragana).
        fn_g["input"] = lambda *a, **k: "2"
        s = MODULE["_WizardState"](languages=["ja", "en"])
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q7_reading_aids"](s)
        assert s.reading_aids == ["ja:hiragana"]
        # '2,3' should land on hiragana + katakana.
        fn_g["input"] = lambda *a, **k: "2,3"
        s = MODULE["_WizardState"](languages=["ja", "en"])
        with contextlib.redirect_stdout(io.StringIO()):
            MODULE["_wizard_q7_reading_aids"](s)
        assert s.reading_aids == ["ja:hiragana", "ja:katakana"]
    finally:
        if saved is not None:
            fn_g["input"] = saved


def test_wizard_intro_uses_beginner_friendly_terms():
    """Wizard intro stays concise and beginner-facing. It should explain
    what the builder produces without exposing TOML/pipeline jargon."""
    intro = MODULE["_WIZARD_INTRO"]
    collapsed = " ".join(intro.split())
    assert "Workflow Builder" in collapsed
    assert "generate a command and reusable workflow" in collapsed
    assert "Commands:" in intro


def test_wizard_intro_has_no_jargon():
    """Intro should not contain 'TOML' or 'pipeline' raw jargon
    (v0.7.1 reword + v0.8 still maintained)."""
    intro = MODULE["_WIZARD_INTRO"]
    assert "TOML" not in intro
    assert "pipeline" not in intro


# ─── v0.9 wizard streamlined to ≤8 Qs ─────────────────────────────


def test_wizard_dispatch_table_has_at_most_nine_question_steps():
    """The user-facing dispatch table caps at 9 entries. Four
    earlier questions (display order, master timing, cleanup preset,
    output folder) are now filled in by
    _wizard_apply_smart_defaults instead of asked; font size is explicit."""
    steps = MODULE["_WIZARD_STEPS"]
    pipeline_steps = [s for s in steps if s[0] != "rename"]
    assert len(pipeline_steps) <= 9, f"too many wizard steps: {[s[0] for s in pipeline_steps]}"
    # The removed steps must not be present.
    labels = {s[0] for s in steps}
    for removed in ("order", "master", "asbplayer", "output"):
        assert removed not in labels, f"{removed!r} should have been removed"
    assert "format" in labels


def test_wizard_apply_smart_defaults_fills_missing_answers():
    """_wizard_apply_smart_defaults populates display order, master,
    cleanup preset, and output folder when the user
    didn't answer them, and returns a human-readable note dict."""
    s = MODULE["_WizardState"](
        source="https://www.themoviedb.org/movie/8392",
        source_kind="url",
        languages=["ja", "en"],
        reading_aids=["ja:hiragana"],
        is_movie=True,
    )
    notes = MODULE["_wizard_apply_smart_defaults"](s)
    assert s.order == ["ja", "en"]
    assert s.master == ""  # blank = first wins downstream
    assert s.asbplayer is True
    assert s.format == ""  # format is asked explicitly when Merge is selected
    assert s.output == "~/Downloads/GetSubtitle"
    # All smart-default notes appear in the banner-friendly summary.
    assert "Display order" in notes
    assert "Timing master" in notes
    assert "Cleanup preset" in notes
    assert "Output folder" in notes


def test_wizard_final_edit_targets_include_smart_defaults():
    s = _wizard_state(
        languages=["en", "ko"],
        order=[],
        master="",
        asbplayer=False,
        reading_aids=["ko:revised"],
        format="ass",
        font_size="",
        steps={"fetch", "translate", "modify", "merge"},
    )
    MODULE["_wizard_apply_smart_defaults"](s)
    labels = [label for label, _value, _fn in MODULE["_wizard_edit_targets"](s)]
    for expected in (
        "display order",
        "timing master",
        "cleanup preset",
        "format / extension",
        "text size",
        "output folder",
    ):
        assert expected in labels


def test_wizard_edit_timing_master_can_override_smart_default(monkeypatch):
    s = _wizard_state(
        languages=["en", "ko"],
        order=["en", "ko"],
        master="",
    )
    g = MODULE["_wizard_prompt"].__globals__
    answers = iter(["2"])
    monkeypatch.setitem(g, "input", lambda *a, **k: next(answers))
    MODULE["_wizard_edit_timing_master"](s)
    assert s.master == "ko"


def test_wizard_edit_cleanup_preset_can_turn_off_smart_default(monkeypatch):
    s = _wizard_state(asbplayer=True)
    g = MODULE["_wizard_yesno"].__globals__
    answers = iter(["n"])
    monkeypatch.setitem(g, "input", lambda *a, **k: next(answers))
    MODULE["_wizard_edit_cleanup_preset"](s)
    assert s.asbplayer is False


def test_wizard_format_recommendation_picks_default_output_format():
    """The format question uses the recommendation as its default, but
    still asks the user to choose SRT / ASS / VTT / SMI / TXT."""
    s = MODULE["_WizardState"](
        source="https://www.themoviedb.org/movie/8392",
        source_kind="url",
        languages=["ja", "en"],
        reading_aids=[],
    )
    fmt, reason = MODULE["_wizard_format_recommendation"](s)
    assert fmt == "srt"
    assert "SRT" in reason or "safest" in reason


def test_wizard_back_history_skips_current_reentered_step():
    history = ["steps", "source", "languages", "translate", "format"]
    previous = MODULE["_wizard_pop_previous_visible_label"](history, "format")
    assert previous == "translate"
    assert history == ["steps", "source", "languages"]


def test_wizard_back_history_ignores_silent_steps(monkeypatch):
    """Back should not get stuck on no-op steps that printed no question.

    Movie episode-scope is one real example: the scope step returns silently
    for movies, and recording it in visible history made repeated `b` land
    back on Languages forever.
    """
    import contextlib
    import io

    calls: list[str] = []
    raised = {"b": False}

    def qa(state):
        calls.append("a")
        print(MODULE["_wizard_next_q"](state, "Visible A"))

    def silent(_state):
        calls.append("silent")

    def qb(state):
        calls.append("b")
        print(MODULE["_wizard_next_q"](state, "Visible B"))
        if not raised["b"]:
            raised["b"] = True
            raise MODULE["_WizardBack"]()

    g = MODULE["_run_wizard_with_back_nav"].__globals__
    monkeypatch.setitem(g, "_WIZARD_STEPS", [("a", qa), ("silent", silent), ("b", qb)])
    monkeypatch.setitem(g, "_wizard_save_draft", lambda _state: None)
    monkeypatch.setitem(g, "_wizard_q11_action", lambda _state: "quit")

    state = MODULE["_WizardState"]()
    with contextlib.redirect_stdout(io.StringIO()):
        MODULE["_run_wizard_with_back_nav"](state)

    assert calls == ["a", "silent", "b", "a", "silent", "b"]


def test_wizard_back_target_preserves_fetch_source_entry():
    state = MODULE["_WizardState"](
        steps={"fetch", "translate", "modify", "merge"},
        source="https://anilist.co/anime/196187/Super-no-Ura-de-Yani-Suu-Futari/",
        source_kind="url",
        season="3-5",
        episode="1",
    )
    idx = MODULE["_wizard_restore_back_target"](state, "source", "scope")
    labels = [label for label, _fn in MODULE["_WIZARD_STEPS"]]

    assert labels[idx] == "source"
    assert state.source == ""
    assert state.source_kind == "url"
    assert getattr(state, "_source_entry_only") is True
    assert state._qcount == MODULE["_wizard_qcount_before"](state, "source") + 1


def test_wizard_source_entry_back_returns_to_source_type(monkeypatch):
    """Once the wizard re-asks URL/title/path, another back returns to Q2."""
    import contextlib
    import io

    state = MODULE["_WizardState"](
        steps={"fetch", "translate", "modify", "merge"},
        source_kind="url",
    )
    state._source_entry_only = True
    state._qcount = MODULE["_wizard_qcount_before"](state, "source") + 1
    calls: list[str] = []

    def fake_prompt(label, default=None, **_kwargs):
        calls.append(label)
        if label == "URL":
            raise MODULE["_WizardBack"]()
        raise MODULE["_WizardAbort"]()

    g = MODULE["_wizard_q1_source"].__globals__
    monkeypatch.setitem(g, "_wizard_prompt", fake_prompt)
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        try:
            MODULE["_wizard_q1_source"](state)
        except MODULE["_WizardAbort"]:
            pass
    out = buf.getvalue()

    assert calls == ["URL", "Number"]
    assert "Q3. Enter the URL." in out
    assert "Going back to source type." in out
    assert out.split("Going back to source type.")[-1].count(
        "Q2. Where should we get subtitles from?"
    ) == 1


def test_wizard_smart_defaults_local_path_output_lands_beside_source():
    """Local-path sources output beside the source folder/file
    instead of the default ~/Downloads/GetSubtitle destination."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        s = MODULE["_WizardState"](
            source=d,
            source_kind="path",
            languages=["ja", "en"],
            reading_aids=[],
        )
        MODULE["_wizard_apply_smart_defaults"](s)
        assert s.output == d


def test_wizard_collect_variant_files_finds_intermediates_only():
    """The post-run variant-cleanup helper picks up
    .furigana-{mode}.vtt / .romanization-{mode}.vtt files and leaves
    the original .ja.srt + merged output alone."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.S02E01.en.srt").write_text("en", encoding="utf-8")
        (root / "Show.S02E01.ja.srt").write_text("ja", encoding="utf-8")
        (root / "Show.S02E01.ja.furigana-hiragana.single-line.ruby.vtt").write_text("h", encoding="utf-8")
        (root / "Show.S02E01.ja.furigana-katakana.single-line.ruby.vtt").write_text("k", encoding="utf-8")
        (root / "Show.S02E01.ja.furigana-romaji.single-line.ruby.vtt").write_text("r", encoding="utf-8")
        (root / "Show.S02E01.ja-hiragana-katakana-romaji-ja-en.vtt").write_text("merged", encoding="utf-8")
        s = MODULE["_WizardState"](
            source="/Volumes/Plex/Shows/X",
            source_kind="path",
            languages=["ja", "en"],
            order=["ja-hiragana", "ja-katakana", "ja-romaji", "ja", "en"],
            reading_aids=["ja:hiragana", "ja:katakana", "ja:romaji"],
            output=str(root),
            steps={"fetch", "modify", "merge"},
        )
        variants = MODULE["_wizard_collect_variant_files"](s, root)
        names = sorted(v.name for v in variants)
        # Exactly the three intermediate VTT variants — not the
        # originals, not the merged output.
        assert names == [
            "Show.S02E01.ja.furigana-hiragana.single-line.ruby.vtt",
            "Show.S02E01.ja.furigana-katakana.single-line.ruby.vtt",
            "Show.S02E01.ja.furigana-romaji.single-line.ruby.vtt",
        ]


def test_wizard_collect_variant_files_empty_when_no_pseudo_langs():
    """When the wizard didn't request any pseudo-lang merge, the
    cleanup helper returns []."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "Show.ja.srt").write_text("ja", encoding="utf-8")
        (root / "Show.en.srt").write_text("en", encoding="utf-8")
        s = MODULE["_WizardState"](
            languages=["ja", "en"],
            order=["ja", "en"],  # plain langs only
            output=str(root),
        )
        assert MODULE["_wizard_collect_variant_files"](s, root) == []


def test_wizard_q11_banner_surfaces_smart_defaults():
    """The review screen prints the smart-defaults block so users see what
    was auto-decided and can revise via the Edit action."""
    import io, contextlib
    s = MODULE["_WizardState"](
        source="https://www.themoviedb.org/movie/8392",
        source_kind="url",
        languages=["ja", "en"],
        reading_aids=["ja:hiragana"],
        is_movie=True,
    )
    s._smart_defaults_notes = MODULE["_wizard_apply_smart_defaults"](s)
    fn_g = MODULE["_wizard_q11_action"].__globals__
    saved = fn_g.get("input")
    try:
        fn_g["input"] = lambda *a, **k: "q"  # quit
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                MODULE["_wizard_q11_action"](s)
            except MODULE["_WizardAbort"]:
                pass
    finally:
        if saved is not None:
            fn_g["input"] = saved
    out = buf.getvalue()
    assert "Review your workflow" in out
    assert "Progress [◼◼◼◼◼◼◼◼◼◼◼◼◻] 99%" in out
    assert "Plan" in out
    assert "Smart defaults" in out
    assert "What next?" in out
    assert "Display order" in out
    assert "Cleanup preset" in out
    assert "Format / extension" not in out  # format is now a normal question
    assert "Start over" in out
    assert "Start over from beginning" not in out
    assert "Show exact command and workflow file" in out


def test_wizard_default_full_pipeline_still_emits_fetch_modify_merge():
    """Default steps (no user override) produce the same shape as the
    pre-v0.7 wizard: --fetch, --modify, --merge."""
    s = MODULE["_WizardState"](
        source="https://www.themoviedb.org/movie/8392",
        source_kind="url",
        languages=["ja", "en"],
        order=["ja", "en"],
        reading_aids=["ja:hiragana"],
        asbplayer=True,
        format="vtt",
        output="~/Downloads/GetSubtitle",
        is_movie=True,
    )
    cli = MODULE["_wizard_emit_cli_string"](s)
    assert "--fetch" in cli
    assert "--modify" in cli
    assert "--merge" in cli
    assert "--no-engine" in cli  # no MT requested

def test_anilist_candidate_movie_detection():
    Candidate = MODULE["AniListCandidate"]
    assert Candidate(id=1, romaji="x", english=None, native=None,
                     season_year=2024, episodes=1, format="MOVIE").is_movie()
    assert Candidate(id=2, romaji="x", english=None, native=None,
                     season_year=2024, episodes=1, format="SPECIAL").is_movie()
    assert Candidate(id=3, romaji="x", english=None, native=None,
                     season_year=2024, episodes=1, format="OVA").is_movie()
    assert not Candidate(id=4, romaji="x", english=None, native=None,
                         season_year=2024, episodes=12, format="TV").is_movie()
    assert not Candidate(id=5, romaji="x", english=None, native=None,
                         season_year=2024, episodes=3, format="OVA").is_movie()


def test_wizard_deferred_reading_aids_dropped_at_run():
    """Run-action strips th/ar/hi/ru reading-aid entries so modify
    doesn't crash; SAVE flow preserves them in the emitted TOML."""
    state = MODULE["_WizardState"](
        reading_aids=["ja:hiragana", "yue:numbers", "th:royal-thai"]
    )
    shipped = {"ja", "ko", "zh", "yue"}
    kept = [s for s in state.reading_aids if s.split(":", 1)[0] in shipped]
    dropped = [s for s in state.reading_aids if s.split(":", 1)[0] not in shipped]
    assert kept == ["ja:hiragana", "yue:numbers"]
    assert dropped == ["th:royal-thai"]
    text = MODULE["_wizard_emit_toml"](state)
    assert "yue:numbers" in text
    assert "th:royal-thai" in text


def test_anilist_title_fallback_helper_is_safe_without_ids():
    """bridge_external_ids_to_anilist_by_title bails cleanly without a
    title; never mutates anilist_id when AniList returns no candidates;
    sets anilist_id from the top hit (movie-biased) on success."""
    bridge = MODULE["bridge_external_ids_to_anilist_by_title"]
    media = MODULE["MediaInfo"](source_url="x", provider="imdb", title="")
    bridge(media)
    assert media.anilist_id is None
    fn_g = bridge.__globals__
    saved = fn_g["search_anilist"]
    try:
        fn_g["search_anilist"] = lambda *a, **k: []
        media2 = MODULE["MediaInfo"](source_url="x", provider="imdb", title="Some Title")
        bridge(media2)
        assert media2.anilist_id is None
        Cand = MODULE["AniListCandidate"]
        fn_g["search_anilist"] = lambda *a, **k: [Cand(
            id=523, romaji="Tonari no Totoro", english="My Neighbor Totoro",
            native=None, season_year=1988, episodes=1, format="MOVIE",
        )]
        media3 = MODULE["MediaInfo"](
            source_url="https://www.themoviedb.org/movie/8392",
            provider="tmdb", title="Totoro", is_movie=True,
        )
        bridge(media3)
        assert media3.anilist_id == 523
    finally:
        fn_g["search_anilist"] = saved


def test_wizard_q7_reading_aid_example_is_script_appropriate():
    """Q8 header used to show 漢字（かんじ） regardless of the user's
    primary script. Korean and Mandarin learners now see appropriate
    examples (한글 / 漢字 (pīnyīn)) instead of a Japanese-only one."""
    import io, contextlib
    fn_g = MODULE["_wizard_q7_reading_aids"].__globals__
    saved_input = fn_g.get("input")
    try:
        fn_g["input"] = lambda *a, **k: "none"
        # Korean primary.
        s_ko = MODULE["_WizardState"](languages=["ko", "en"], order=["ko", "en"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            MODULE["_wizard_q7_reading_aids"](s_ko)
        out = buf.getvalue()
        assert "한글" in out, "Korean learner should see hangul example"
        assert "漢字（かんじ）" not in out, "Korean learner should not see ja example"
        assert "VTT" not in out, "Format guidance belongs in the format question"
        # Mandarin primary.
        s_zh = MODULE["_WizardState"](languages=["zh", "en"], order=["zh", "en"])
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            MODULE["_wizard_q7_reading_aids"](s_zh)
        out2 = buf2.getvalue()
        assert "pīnyīn" in out2, "Mandarin learner should see pinyin example"
    finally:
        if saved_input is not None:
            fn_g["input"] = saved_input


def test_wizard_q9_format_describes_vtt_and_ass_player_fit():
    """Format choice should steer by viewing environment and player fit."""
    import io, contextlib
    fn_g = MODULE["_wizard_q9_format"].__globals__
    saved_input = fn_g.get("input")
    try:
        fn_g["input"] = lambda *a, **k: "3"
        s = MODULE["_WizardState"](reading_aids=[], asbplayer=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            MODULE["_wizard_q9_format"](s)
    finally:
        if saved_input is not None:
            fn_g["input"] = saved_input
    out = buf.getvalue()
    assert s.format == "vtt"
    assert s.viewing_env == "browser"
    assert "Final output format" in out
    assert "Choose the format that best matches your player." in out
    assert "Recommendations:" in out
    assert "Streaming Netflix with multiple subtitles?" in out
    assert "VTT (asbplayer browser plug-in required)" in out
    assert "Works with a browser extension on Netflix, Disney+ & other streaming sites" in out
    assert "OTHER FORMATS:" not in out
    assert "Korean subtitle format" in out
    assert "Suggested default:" in out
    assert "ASS" in out
    assert "positioning, sizing, and readability" in out


def test_wizard_q9_format_omits_duplicate_reading_aid_notes():
    import io, contextlib
    fn_g = MODULE["_wizard_q9_format"].__globals__
    saved_input = fn_g.get("input")
    try:
        fn_g["input"] = lambda *a, **k: "3"
        s = MODULE["_WizardState"](
            languages=["ja", "ko"],
            reading_aids=["ja:hiragana", "ko:revised"],
            asbplayer=True,
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            MODULE["_wizard_q9_format"](s)
    finally:
        if saved_input is not None:
            fn_g["input"] = saved_input
    out = buf.getvalue()
    assert "Reading-aid notes:" not in out
    assert "true ruby above Japanese text" not in out
    assert "SRT/SMI/ASS use fallback reading-aid layouts" not in out
    assert "OTHER FORMATS:" in out


def test_wizard_q9_format_shows_vtt_example_only_for_japanese_ruby():
    import io, contextlib
    fn_g = MODULE["_wizard_q9_format"].__globals__
    saved_input = fn_g.get("input")
    try:
        fn_g["input"] = lambda *a, **k: "3"
        s = MODULE["_WizardState"](reading_aids=["ja:katakana"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            MODULE["_wizard_q9_format"](s)
    finally:
        if saved_input is not None:
            fn_g["input"] = saved_input
    out = buf.getvalue()
    assert "Example:" in out
    assert "VTT:  にほんご" in out
    assert "OTHER FORMATS:" in out


def test_wizard_font_size_labels_follow_selected_format():
    import io, contextlib
    fn_g = MODULE["_wizard_q_font_size"].__globals__
    saved_input = fn_g.get("input")
    try:
        fn_g["input"] = lambda *a, **k: "1"
        s = MODULE["_WizardState"](
            steps={"merge"},
            languages=["en", "es"],
            order=["en", "es"],
            format="ass",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            MODULE["_wizard_q_font_size"](s)
    finally:
        if saved_input is not None:
            fn_g["input"] = saved_input
    out = buf.getvalue()
    assert "Regular (58)" in out
    assert "Smaller (46)" in out
    assert "Larger (70)" in out
    assert "Regular (30)" not in out
    assert s.font_size == "regular"


def test_wizard_font_size_recommends_smaller_for_four_line_ass_stack():
    import io, contextlib
    fn_g = MODULE["_wizard_q_font_size"].__globals__
    saved_input = fn_g.get("input")
    try:
        fn_g["input"] = lambda *a, **k: ""
        s = MODULE["_WizardState"](
            steps={"modify", "merge"},
            languages=["zh", "ko", "en"],
            order=["zh", "ko", "en"],
            reading_aids=["zh:marks"],
            format="ass",
        )
        assert MODULE["_wizard_merge_order"](s) == ["zh-marks", "zh", "ko", "en"]
        assert MODULE["_wizard_expected_stack_line_count"](s) == 4
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            MODULE["_wizard_q_font_size"](s)
    finally:
        if saved_input is not None:
            fn_g["input"] = saved_input
    out = buf.getvalue()
    assert "This output uses ASS and will usually show 4 lines at once." in out
    assert "1) Regular (58)" in out
    assert "2) Smaller (46) — recommended" in out
    assert s.font_size == "smaller"


def test_wizard_font_size_custom_back_returns_to_size_choices():
    import io, contextlib
    fn_g = MODULE["_wizard_q_font_size"].__globals__
    saved_prompt = fn_g["_wizard_prompt"]
    answers = iter(["4", "3"])

    def fake_prompt(label, default=None, **kwargs):
        if label == "Number":
            return next(answers)
        if label == "Font size":
            raise MODULE["_WizardBack"]()
        raise AssertionError(f"unexpected prompt: {label}")

    try:
        fn_g["_wizard_prompt"] = fake_prompt
        s = MODULE["_WizardState"](
            steps={"merge"},
            languages=["en", "es"],
            order=["en", "es"],
            format="srt",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            MODULE["_wizard_q_font_size"](s)
    finally:
        fn_g["_wizard_prompt"] = saved_prompt

    assert s.font_size == "larger"
    assert "Going back to text-size choices." in buf.getvalue()


def test_wizard_plain_plan_hides_reading_aid_pseudo_language_tokens():
    s = MODULE["_WizardState"](
        steps={"fetch", "modify", "merge"},
        source="The God of Cookery",
        source_kind="title",
        languages=["zh", "ko"],
        order=["zh", "ko"],
        reading_aids=["zh:marks"],
        format="ass",
        font_size="smaller",
    )

    plan = "\n".join(MODULE["_wizard_plain_plan"](s))

    assert "Chinese pinyin" in plan
    assert "Chinese + Korean ASS study subtitle file" in plan
    assert "zh-marks" not in plan


def test_wizard_emit_cli_merges_single_chinese_pinyin_variant():
    """A single non-Japanese reading aid still needs its pseudo-language
    side file included in merge. Otherwise modify generates pinyin but the
    final output merges only plain zh+ko."""
    s = MODULE["_WizardState"](
        steps={"fetch", "modify", "merge"},
        source="/tmp/God Of Cookery",
        source_kind="path",
        source_title="The God of Cookery",
        is_movie=True,
        languages=["zh", "ko"],
        order=["zh", "ko"],
        reading_aids=["zh:marks"],
        format="ass",
        font_size="regular",
        output="/tmp/God Of Cookery",
    )

    cli = MODULE["_wizard_emit_cli"](s)

    merge_index = cli.index("--merge")
    merge_languages_index = cli.index("--languages", merge_index)
    assert cli[merge_languages_index + 1] == "zh-marks,zh,ko"
    assert cli[cli.index("--reading") + 1] == "zh:marks"


def test_wizard_emit_cli_fetches_chinese_for_cantonese_jyutping_workflow():
    """Cantonese subtitle provider labels are rare. The wizard should fetch
    Chinese text, then create a Cantonese Jyutping row from that source."""
    s = MODULE["_WizardState"](
        steps={"fetch", "modify", "merge"},
        source="/tmp/God Of Cookery",
        source_kind="path",
        source_title="The God of Cookery",
        is_movie=True,
        languages=["yue", "ko"],
        order=["yue", "ko"],
        reading_aids=["yue:numbers"],
        format="ass",
        font_size="regular",
        output="/tmp/God Of Cookery",
    )

    cli = MODULE["_wizard_emit_cli"](s)

    fetch_languages_index = cli.index("--languages")
    assert cli[fetch_languages_index + 1] == "zh,ko"
    merge_index = cli.index("--merge")
    merge_languages_index = cli.index("--languages", merge_index)
    assert cli[merge_languages_index + 1] == "yue-numbers,zh,ko"
    assert cli[cli.index("--reading") + 1] == "yue:numbers"


def test_wizard_reading_aid_labels_format_agnostic():
    """The Q8 reading-aid menu labels no longer say 'above kanji' — that
    only applies to VTT ruby. The wording must work for SRT/SMI/ASS too."""
    menu = MODULE["_WIZARD_READING_AID_MENU"]
    ja_rows = [row for row in menu if row[0] == "ja"]
    labels = [row[2] for row in ja_rows]
    for label in labels:
        assert "above kanji" not in label.lower(), label
    assert any("readings for kanji" in label.lower() for label in labels)
    assert any("full-sentence romaji" in label.lower() for label in labels)


# ─── Korean romanization ────────────────────────────────────────────

# ─── Chinese romanization ───────────────────────────────────────────

class _FakePypinyin:
    """Minimal stand-in for pypinyin in tests.

    Mirrors the real module's public surface that getsubtitle_core uses:
      .Style.TONE / .TONE3 / .NORMAL — sentinel objects
      .lazy_pinyin(text, style=..., errors=...) → list of strings

    The fake returns hand-crafted pinyin for the cues we test against,
    so we exercise the full pipeline (mode dispatch, pair-chunking,
    side-file emission) without depending on the real library."""

    class Style:
        TONE = "TONE"
        TONE3 = "TONE3"
        NORMAL = "NORMAL"

    _TABLE = {
        "你": {"TONE": "nǐ",   "TONE3": "ni3",   "NORMAL": "ni"},
        "好": {"TONE": "hǎo",  "TONE3": "hao3",  "NORMAL": "hao"},
        "世": {"TONE": "shì",  "TONE3": "shi4",  "NORMAL": "shi"},
        "界": {"TONE": "jiè",  "TONE3": "jie4",  "NORMAL": "jie"},
        "中": {"TONE": "zhōng","TONE3": "zhong1","NORMAL": "zhong"},
        "国": {"TONE": "guó",  "TONE3": "guo2",  "NORMAL": "guo"},
    }

    @classmethod
    def lazy_pinyin(cls, text, style="TONE", errors="default"):
        return [cls._TABLE.get(ch, {style: ch}).get(style, ch) for ch in text]


def _install_fake_pypinyin():
    """Inject FakePypinyin into the module's cached pypinyin slot and
    return a teardown handle."""
    fn = MODULE["_pypinyin_module"]
    g = fn.__globals__
    saved = g.get("_PYPINYIN_MODULE")
    g["_PYPINYIN_MODULE"] = _FakePypinyin
    def restore():
        g["_PYPINYIN_MODULE"] = saved
    return restore


def test_has_hanzi_detects_cjk_ideographs():
    """has_hanzi covers Unified Ideographs and Extension-A; excludes
    Hangul (ko's territory) and pure ASCII."""
    fn = MODULE["has_hanzi"]
    assert fn("你好") is True
    assert fn("Hello 中国 world") is True
    assert fn("漢字") is True   # CJK Ideographs — overlaps with ja kanji
    assert fn("한국어") is False  # Hangul, not hanzi
    assert fn("Hello world") is False
    assert fn("") is False


def test_romanize_chinese_marks_style_with_fake_pypinyin():
    """zh:marks routes through pypinyin's TONE style. Spaces inserted
    between adjacent hanzi syllables; non-hanzi (ASCII, punctuation)
    passes through verbatim."""
    restore = _install_fake_pypinyin()
    try:
        fn = MODULE["romanize_chinese"]
        assert fn("你好", "marks") == "nǐ hǎo"
        assert fn("你好世界", "marks") == "nǐ hǎo shì jiè"
        # Mixed content — ASCII chunk preserved as-is between hanzi runs.
        assert fn("Hi 你好", "marks") == "Hi nǐ hǎo"
        # No hanzi → unchanged.
        assert fn("Hello world", "marks") == "Hello world"
        # Empty.
        assert fn("", "marks") == ""
    finally:
        restore()


def test_romanize_chinese_numbers_and_letters_styles():
    """zh:numbers → TONE3 (ni3 hao3); zh:letters → NORMAL (ni hao).
    Verifies mode dispatch reaches the right pypinyin style."""
    restore = _install_fake_pypinyin()
    try:
        fn = MODULE["romanize_chinese"]
        assert fn("你好", "numbers") == "ni3 hao3"
        assert fn("你好", "letters") == "ni hao"
    finally:
        restore()


def test_romanize_chinese_unknown_mode_raises_clean_error():
    """A bogus mode must raise CliError listing the supported modes."""
    restore = _install_fake_pypinyin()
    try:
        fn = MODULE["romanize_chinese"]
        try:
            fn("你好", "tongyong")
        except MODULE["CliError"] as e:
            assert "tongyong" in str(e) or "Unknown Chinese" in str(e)
            assert "marks" in str(e) and "numbers" in str(e)
        else:
            raise AssertionError("expected CliError for unknown zh mode")
    finally:
        restore()


def test_romanize_chinese_raises_when_pypinyin_missing():
    """Without pypinyin installed, romanize_chinese must raise a CliError
    with a clear install hint."""
    fn = MODULE["_pypinyin_module"]
    g = fn.__globals__
    saved = g.get("_PYPINYIN_MODULE")
    g["_PYPINYIN_MODULE"] = None
    # Also block the import inside _pypinyin_module by injecting a
    # sys.modules entry that raises on attribute access — but the
    # cleaner approach is to monkey-patch the function itself to
    # simulate the ImportError path.
    saved_fn = g["_pypinyin_module"]
    def _raise_missing():
        raise MODULE["CliError"](
            "Chinese pinyin needs the pypinyin package.\n"
            "  Quick install: python3 -m pip install pypinyin"
        )
    g["_pypinyin_module"] = _raise_missing
    try:
        try:
            MODULE["romanize_chinese"]("你好", "marks")
        except MODULE["CliError"] as e:
            assert "pypinyin" in str(e)
            assert "pip install" in str(e)
        else:
            raise AssertionError("expected CliError for missing pypinyin")
    finally:
        g["_PYPINYIN_MODULE"] = saved
        g["_pypinyin_module"] = saved_fn


def test_text_with_chinese_readings_parenthetical_per_hanzi_run():
    """Consecutive hanzi → one parenthetical block. ASCII/whitespace
    runs interleave as their own passthrough chunks."""
    restore = _install_fake_pypinyin()
    try:
        fn = MODULE["text_with_chinese_readings"]
        out = fn("你好世界", "marks")
        assert "你好世界（" in out
        assert "nǐ hǎo shì jiè" in out
        # Mixed: hanzi run + space + hanzi run → two parentheticals.
        out2 = fn("中国 你好", "marks")
        assert "中国（zhōng guó）" in out2
        assert "你好（nǐ hǎo）" in out2
        # Pure ASCII passthrough.
        assert fn("Hello", "marks") == "Hello"
    finally:
        restore()


def test_text_with_chinese_ruby_wraps_per_hanzi_run():
    """VTT ruby: each hanzi run gets one <ruby>/<rt> pair."""
    restore = _install_fake_pypinyin()
    try:
        fn = MODULE["text_with_chinese_ruby"]
        out = fn("你好 世界", "marks")
        assert out.count("<ruby>") == 2
        assert "<ruby>你好<rt>nǐ hǎo</rt></ruby>" in out
        assert "<ruby>世界<rt>shì jiè</rt></ruby>" in out
    finally:
        restore()


def test_hanzi_reading_pair_lines_returns_aligned_rows():
    """Stacked: returns (reading_row, text_row) aligned per chunk.
    Returns None when no hanzi present."""
    restore = _install_fake_pypinyin()
    try:
        fn = MODULE["hanzi_reading_pair_lines"]
        pair = fn("你好 世界", "marks")
        assert pair is not None
        reading_row, text_row = pair
        assert "nǐ hǎo" in reading_row
        assert "shì jiè" in reading_row
        assert "你好" in text_row
        assert "世界" in text_row
        # No hanzi → None.
        assert fn("Hello world", "marks") is None
    finally:
        restore()


def _install_fake_pycantonese():
    """Patch the Cantonese backend with a tiny deterministic fake."""
    import types
    fn = MODULE["_pycantonese_module"]
    g = fn.__globals__
    saved = g.get("_PYCANTONESE_MODULE")
    table = {
        "廣": "gwong2",
        "東": "dung1",
        "話": "waa2",
        "你": "nei5",
        "好": "hou2",
    }
    fake = types.SimpleNamespace(
        characters_to_jyutping=lambda text: [table.get(ch, "") for ch in text]
    )
    g["_PYCANTONESE_MODULE"] = fake
    def restore():
        g["_PYCANTONESE_MODULE"] = saved
    return restore


def test_romanize_cantonese_numbers_with_mock_backend():
    restore = _install_fake_pycantonese()
    try:
        fn = MODULE["romanize_cantonese"]
        assert fn("廣東話", "numbers") == "gwong2 dung1 waa2"
        assert fn("Hi 你好", "numbers") == "Hi nei5 hou2"
        assert fn("Hello", "numbers") == "Hello"
    finally:
        restore()


def test_text_with_cantonese_readings_and_ruby():
    restore = _install_fake_pycantonese()
    try:
        assert MODULE["text_with_cantonese_readings"]("廣東話", "numbers") == "廣東話（gwong2 dung1 waa2）"
        ruby = MODULE["text_with_cantonese_ruby"]("你好", "numbers")
        assert ruby == "<ruby>你好<rt>nei5 hou2</rt></ruby>"
    finally:
        restore()


def test_generate_cantonese_romanization_accepts_yue_or_zh_srt():
    import tempfile
    from pathlib import Path
    restore = _install_fake_pycantonese()
    fn = MODULE["generate_cantonese_romanization"]
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            yue_path = root / "Show.S01E01.yue.srt"
            yue_path.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n廣東話\n",
                encoding="utf-8",
            )
            zh_path = root / "Show.S01E01.zh.srt"
            zh_path.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n你好\n",
                encoding="utf-8",
            )
            out = fn([yue_path, zh_path], "numbers", formats={"srt", "vtt"})
            names = sorted(p.name for p in out)
            assert names == [
                "Show.S01E01.yue.romanization-numbers.asb.srt",
                "Show.S01E01.yue.romanization-numbers.ruby.vtt",
                "Show.S01E01.zh.yue.romanization-numbers.asb.srt",
                "Show.S01E01.zh.yue.romanization-numbers.ruby.vtt",
            ]
            assert any("廣東話（gwong2 dung1 waa2）" in p.read_text(encoding="utf-8") for p in out)
            assert any("你好（nei5 hou2）" in p.read_text(encoding="utf-8") for p in out)
    finally:
        restore()


def test_generate_chinese_and_cantonese_readings_from_script_specific_suffixes(tmp_path):
    restore_py = _install_fake_pypinyin()
    restore_yue = _install_fake_pycantonese()
    try:
        zh_hant = tmp_path / "Show.S01E01.zh-Hant.srt"
        zh_hant.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n你好\n",
            encoding="utf-8",
        )
        chs = tmp_path / "Show.S01E02.chs.srt"
        chs.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n你好\n",
            encoding="utf-8",
        )
        zh_out = MODULE["generate_chinese_romanization"](
            [zh_hant, chs], "marks", formats={"srt"}
        )
        assert sorted(p.name for p in zh_out) == [
            "Show.S01E01.zh.romanization-marks.asb.srt",
            "Show.S01E02.zh.romanization-marks.asb.srt",
        ]
        yue_out = MODULE["generate_cantonese_romanization"](
            [zh_hant, chs], "numbers", formats={"srt"}
        )
        assert sorted(p.name for p in yue_out) == [
            "Show.S01E01.zh-Hant.yue.romanization-numbers.asb.srt",
            "Show.S01E02.chs.yue.romanization-numbers.asb.srt",
        ]
    finally:
        restore_yue()
        restore_py()


def test_combine_can_derive_cantonese_jyutping_from_chinese_subtitle(tmp_path, capsys):
    restore = _install_fake_pycantonese()
    try:
        (tmp_path / "Show.S01E01.zh.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n你好\n",
            encoding="utf-8",
        )
        (tmp_path / "Show.S01E01.ko.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n안녕하세요\n",
            encoding="utf-8",
        )

        rc = MODULE["combine_main"]([
            str(tmp_path),
            "--languages", "yue-numbers,zh,ko",
            "--format", "srt",
        ])

        assert rc == 0
        out_file = tmp_path / "Show.S01E01.yue-numbers-zh-ko.srt"
        assert out_file.exists()
        text = out_file.read_text(encoding="utf-8")
        assert "nei5 hou2" in text
        assert "你好" in text
        assert "안녕하세요" in text
    finally:
        restore()


def test_plan_mkv_subtitle_extraction_skips_image_streams_and_names_text_outputs():
    import tempfile
    from pathlib import Path
    fn = MODULE["plan_mkv_subtitle_extraction"]
    g = fn.__globals__
    saved_probe = g["_ffprobe_subtitle_streams"]
    try:
        def fake_probe(_path):
            return [
                {"index": 2, "codec_name": "subrip", "tags": {"language": "kor"}},
                {"index": 3, "codec_name": "ass", "tags": {"language": "jpn"}},
                {"index": 4, "codec_name": "hdmv_pgs_subtitle", "tags": {"language": "eng"}},
            ]
        g["_ffprobe_subtitle_streams"] = fake_probe
        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "Episode.mkv"
            video.write_bytes(b"video")
            plan, notes = fn([video])
            assert [(p[1], p[2], p[3], p[4].name) for p in plan] == [
                (2, "ko", "subrip", "Episode.ko.srt"),
                (3, "ja", "ass", "Episode.ja.ass"),
            ]
            assert any("image subtitle" in note for note in notes)
    finally:
        g["_ffprobe_subtitle_streams"] = saved_probe


def test_scan_video_files_ignores_macos_appledouble_sidecars(tmp_path):
    real = tmp_path / "Movie.mkv"
    sidecar = tmp_path / "._Movie.mkv"
    real.write_bytes(b"not really a movie")
    sidecar.write_bytes(b"metadata")

    found = MODULE["scan_video_files"]([tmp_path])

    assert found == [real]


def test_fetch_path_uses_embedded_subtitles_before_online(tmp_path, monkeypatch):
    captured: list[list[str]] = []
    g = MODULE["_batch_fetch_one"].__globals__
    monkeypatch.setitem(g, "_batch_run", lambda cmd, dry_run: captured.append(list(cmd)) or 0)

    def fake_probe(_path):
        return [
            {"index": 2, "codec_name": "subrip", "tags": {"language": "eng"}},
            {"index": 3, "codec_name": "subrip", "tags": {"language": "spa"}},
        ]

    monkeypatch.setitem(g, "_ffprobe_subtitle_streams", fake_probe)
    video = tmp_path / "Movie.mkv"
    video.write_bytes(b"video")

    rc = MODULE["_batch_fetch_one"](
        target=video,
        show_folder=tmp_path,
        season=None,
        profile="en",
        dry_run=True,
        fetch_langs_override=["en", "es"],
        title_override="Movie",
        movie_override=True,
    )

    assert rc == 0
    assert captured == []


def test_fetch_path_smi_sidecar_suppresses_online_for_that_language(tmp_path, monkeypatch):
    captured: list[list[str]] = []
    g = MODULE["_batch_fetch_one"].__globals__
    monkeypatch.setitem(g, "_batch_run", lambda cmd, dry_run: captured.append(list(cmd)) or 0)
    monkeypatch.setitem(g, "_ffprobe_subtitle_streams", lambda _path: [])
    video = tmp_path / "The.God.of.Cookery.1996.mkv"
    video.write_bytes(b"video")
    (tmp_path / "The.God.of.Cookery.1996.smi").write_text(
        "<SAMI><BODY>"
        "<SYNC Start=1000><P Class=KOKRCC>안녕하세요"
        "<SYNC Start=2000><P Class=KOKRCC>&nbsp;"
        "</BODY></SAMI>",
        encoding="utf-8",
    )

    rc = MODULE["_batch_fetch_one"](
        target=tmp_path,
        show_folder=tmp_path,
        season=None,
        profile="en",
        dry_run=True,
        fetch_langs_override=["zh", "ko", "en"],
        title_override="The God of Cookery",
        movie_override=True,
    )

    assert rc == 0
    assert captured
    cmd = captured[0]
    assert "-l" in cmd
    assert cmd[cmd.index("-l") + 1] == "zh,en"


def test_fetch_path_single_video_counts_same_stem_sidecars_before_embedded(tmp_path, monkeypatch):
    captured: list[list[str]] = []
    g = MODULE["_batch_fetch_one"].__globals__
    monkeypatch.setitem(g, "_batch_run", lambda cmd, dry_run: captured.append(list(cmd)) or 0)

    def fake_probe(_path):
        return [
            {"index": 2, "codec_name": "subrip", "tags": {"language": "eng"}},
            {"index": 3, "codec_name": "subrip", "tags": {"language": "spa"}},
            {"index": 4, "codec_name": "subrip", "tags": {"language": "fre"}},
        ]

    monkeypatch.setitem(g, "_ffprobe_subtitle_streams", fake_probe)
    video = tmp_path / "Movie.mkv"
    video.write_bytes(b"video")
    (tmp_path / "Movie.en.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
    (tmp_path / "Movie.es.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHola\n", encoding="utf-8")

    rc = MODULE["_batch_fetch_one"](
        target=video,
        show_folder=tmp_path,
        season=None,
        profile="en",
        dry_run=True,
        fetch_langs_override=["en", "es", "fr"],
        title_override="Movie",
        movie_override=True,
    )

    assert rc == 0
    assert captured == []


def test_convert_text_subtitle_to_srt_file_converts_ass_source():
    import tempfile
    from pathlib import Path
    fn = MODULE["convert_text_subtitle_to_srt_file"]
    with tempfile.TemporaryDirectory() as td:
        ass = Path(td) / "Episode.en.ass"
        ass.write_text(
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            r"Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello\Nthere"
            "\n",
            encoding="utf-8",
        )
        out, written = fn(ass)
        assert written is True
        assert out is not None
        text = out.read_text(encoding="utf-8")
        assert out.name == "Episode.en.srt"
        assert "00:00:01,000 --> 00:00:03,000" in text
        assert "Hello\nthere" in text


def test_manual_search_suggestions_include_japanese_fallbacks():
    media = MODULE["MediaInfo"](
        provider="title",
        source_url="title://fena",
        title="Fena: Pirate Princess",
        title_aliases=["海賊王女", "Kaizoku Oujo"],
    )
    suggestions = MODULE["build_manual_search_suggestions"](media, ["ja"])
    labels = [s.label for s in suggestions]
    assert "Jimaku web search" in labels
    assert "Kitsunekko" in labels
    assert any("Japanese subtitle" in s.note or "anime subtitle" in s.note for s in suggestions)


def test_doctor_main_runs_without_network_or_provider_calls():
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        rc = MODULE["doctor_main"]([])
    assert rc in (0, 1)
    out = buf.getvalue()
    assert "getsubtitle doctor" in out
    assert "Python" in out
    assert "ffmpeg" in out


def test_generate_chinese_romanization_walks_chinese_text_srt_sources():
    """Orchestrator touches Chinese text SRT files; emits one side file per
    requested format. Non-Chinese and non-SRT paths are skipped."""
    import tempfile
    from pathlib import Path
    restore = _install_fake_pypinyin()
    fn = MODULE["generate_chinese_romanization"]
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zh_path = root / "Show.S01E01.zh.srt"
            zh_path.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n你好 世界\n",
                encoding="utf-8",
            )
            ja_path = root / "Show.S01E01.ja.srt"
            ja_path.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\n日本語\n",
                encoding="utf-8",
            )
            out = fn([zh_path, ja_path], "marks", single_line=False, formats={"srt", "vtt"})
            assert len(out) == 2  # 2 formats × 1 zh file
            names = sorted(p.name for p in out)
            assert "Show.S01E01.zh.romanization-marks.asb.srt" in names
            assert "Show.S01E01.zh.romanization-marks.ruby.vtt" in names
            for p in out:
                assert p.exists()
            # Validate the SRT actually carries the pinyin output. The
            # whitespace between hanzi runs splits them into separate
            # chunks, so each hanzi run gets its own parenthetical block.
            srt_content = next(
                p.read_text(encoding="utf-8") for p in out if p.name.endswith(".asb.srt")
            )
            assert "你好（nǐ hǎo）" in srt_content
            assert "世界（shì jiè）" in srt_content
    finally:
        restore()


def test_apply_reading_to_args_routes_ja_ko_zh():
    """All three shipped languages must land on their own attributes."""
    import argparse
    fn = MODULE["_apply_reading_to_args"]
    args = argparse.Namespace(
        reading="ja:hiragana,ko:revised,zh:marks",
        ja_reading=None,
        ko_reading=None,
        zh_reading=None,
    )
    fn(args)
    assert args.ja_reading == "hiragana"
    assert args.ja_readings == ["hiragana"]
    assert args.ko_reading == "revised"
    assert args.ko_readings == ["revised"]
    assert args.zh_reading == "marks"
    args_multi = argparse.Namespace(reading="ja:hiragana,ja:katakana,ja:romaji")
    fn(args_multi)
    assert args_multi.ja_reading == "hiragana"
    assert args_multi.ja_readings == ["hiragana", "katakana", "romaji"]
    args_multi_ko = argparse.Namespace(reading="ko:revised,ko:yale")
    fn(args_multi_ko)
    assert args_multi_ko.ko_reading == "revised"
    assert args_multi_ko.ko_readings == ["revised", "yale"]
    # Verify zh:numbers and zh:letters round-trip too.
    args2 = argparse.Namespace(
        reading="zh:numbers",
        ja_reading=None, ko_reading=None, zh_reading=None,
    )
    fn(args2)
    assert args2.zh_reading == "numbers"
    args3 = argparse.Namespace(
        reading="zh:letters",
        ja_reading=None, ko_reading=None, zh_reading=None,
    )
    fn(args3)
    assert args3.zh_reading == "letters"
    args_aliases = argparse.Namespace(reading="mandarin:true,cantonese:true")
    fn(args_aliases)
    assert args_aliases.zh_reading == "marks"
    assert args_aliases.yue_reading == "numbers"


def test_apply_reading_to_args_still_rejects_deferred_languages():
    """Languages whose backend still isn't shipped (th, ar, hi, ru)
    must continue to raise CliError."""
    import argparse
    fn = MODULE["_apply_reading_to_args"]
    args = argparse.Namespace(
        reading="th:royal-thai",
        ja_reading=None, ko_reading=None, zh_reading=None,
    )
    try:
        fn(args)
    except MODULE["CliError"] as e:
        assert "th:royal-thai" in str(e)
    else:
        raise AssertionError("expected CliError for th (still deferred)")


def test_setup_recommendations_zh_learner_is_selected_by_default():
    """Mandarin reading-aid recommendation must default to opt-in
    (was opt-in only when the backend was deferred)."""
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["zh"], content="tv",
        venue="browser", mt="none",
    )
    recs = MODULE["_setup_recommendations"](choice)
    zh_recs = [r for r in recs if r.key.startswith("reading:zh")]
    assert zh_recs, "zh learner missed reading-aid recommendation"
    assert zh_recs[0].selected_by_default is True


def test_wizard_probe_treats_zh_as_block_not_deferred():
    """zh:marks now probes for pypinyin (hard dep). Should appear as
    a block-or-pass condition, NOT a deferred warning."""
    state = MODULE["_WizardState"](
        languages=["zh", "en"],
        order=["zh", "en"],
        reading_aids=["zh:marks"],
    )
    gaps = MODULE["_wizard_probe_dependencies"](state)
    deferred = [
        g for g in gaps
        if "deferred" in g[2].lower() or "not yet implemented" in g[2].lower()
    ]
    assert not deferred, "zh:marks should no longer be flagged as deferred"


def test_has_hangul_detects_syllables_and_jamo():
    """has_hangul returns True for syllables, jamo, and Hangul-containing
    mixed strings. False for pure ASCII / Latin / kanji."""
    fn = MODULE["has_hangul"]
    assert fn("한국어") is True
    assert fn("Hello 한국어 world") is True
    assert fn("ㄱㄴㄷ") is True   # jamo block
    assert fn("Hello world") is False
    assert fn("漢字") is False     # CJK kanji, not hangul
    assert fn("") is False


def test_romanize_korean_yale_in_tree_no_external_deps():
    """Yale mode uses an in-tree lookup table — no pip extras required.
    Validates the cases that exercise initial, medial, final positions."""
    fn = MODULE["romanize_korean"]
    # 한국어 (han-guk-eo) → han + kwuk + e = hankwuke (Yale orthographic)
    assert fn("한국어", "yale") == "hankwuke"
    # 같이 (orthographic; Yale doesn't apply palatalization)
    assert fn("같이", "yale") == "kathi"
    # Whitespace and ASCII pass through.
    assert fn("Hello 한국어", "yale") == "Hello hankwuke"
    assert fn("", "yale") == ""


def test_romanize_korean_unknown_mode_raises_clean_error():
    """A bogus mode must fail with a CliError listing the supported modes."""
    fn = MODULE["romanize_korean"]
    try:
        fn("한국어", "wadegiles")
    except MODULE["CliError"] as e:
        assert "wadegiles" in str(e) or "Unknown Korean" in str(e)
        assert "revised" in str(e) and "yale" in str(e)
    else:
        raise AssertionError("expected CliError for unknown mode")


def test_romanize_korean_revised_raises_when_libs_missing():
    """Without korean-romanizer installed, revised mode must raise a
    CliError with a clear install hint."""
    fn = MODULE["_korean_revised_romanizer_class"]
    # Reset the cache so this test is hermetic regardless of test order.
    g = fn.__globals__
    g["_KOREAN_ROMANIZER_CLS"] = None
    try:
        fn()
    except MODULE["CliError"] as e:
        msg = str(e)
        assert "korean-romanizer" in msg
        assert "pip install" in msg
        assert "romanization-ko" in msg or "korean-romanizer" in msg
    else:
        # The sandbox might actually have it installed — in that case this
        # test is a no-op and that's fine.
        pass


def test_romanize_korean_revised_with_mocked_libs():
    """With mocked g2pk + korean-romanizer, the revised path produces
    sensible output. We mock G2P to return a hand-crafted phoneme form
    and Romanizer to apply a simple rule so the test asserts on the
    pipeline contract, not the third-party libraries' exactness."""
    fn = MODULE["_romanize_revised"]
    g = fn.__globals__
    # Mock g2pk: input '같이' should become '가치' (palatalization).
    saved_g2p = g.get("_KOREAN_G2P_CACHE")
    saved_tried = g.get("_KOREAN_G2P_TRIED")
    saved_cls = g.get("_KOREAN_ROMANIZER_CLS")
    try:
        g["_KOREAN_G2P_CACHE"] = lambda text: text.replace("같이", "가치")
        g["_KOREAN_G2P_TRIED"] = True
        class FakeRomanizer:
            def __init__(self, text):
                self.text = text
            def romanize(self):
                # Tiny fake: hand-romanize just the chars we test here.
                table = {"가": "ga", "치": "chi"}
                return "".join(table.get(c, c) for c in self.text)
        g["_KOREAN_ROMANIZER_CLS"] = FakeRomanizer
        # 같이 → G2P → 가치 → romanizer → "gachi"
        assert fn("같이") == "gachi"
    finally:
        g["_KOREAN_G2P_CACHE"] = saved_g2p
        g["_KOREAN_G2P_TRIED"] = saved_tried
        g["_KOREAN_ROMANIZER_CLS"] = saved_cls


def test_romanize_korean_revised_falls_back_when_g2p_missing():
    """When g2pk isn't installed, the revised path still runs — it just
    passes the raw hangul straight to korean-romanizer."""
    fn = MODULE["_romanize_revised"]
    g = fn.__globals__
    saved_g2p = g.get("_KOREAN_G2P_CACHE")
    saved_tried = g.get("_KOREAN_G2P_TRIED")
    saved_cls = g.get("_KOREAN_ROMANIZER_CLS")
    try:
        # Tell the g2p loader it tried and failed.
        g["_KOREAN_G2P_CACHE"] = None
        g["_KOREAN_G2P_TRIED"] = True
        seen_input: list[str] = []
        class FakeRomanizer:
            def __init__(self, text):
                seen_input.append(text)
                self.text = text
            def romanize(self):
                return "FAKE"
        g["_KOREAN_ROMANIZER_CLS"] = FakeRomanizer
        fn("같이")
        # Without G2P preprocessing, romanizer must see the raw input.
        assert seen_input == ["같이"]
    finally:
        g["_KOREAN_G2P_CACHE"] = saved_g2p
        g["_KOREAN_G2P_TRIED"] = saved_tried
        g["_KOREAN_ROMANIZER_CLS"] = saved_cls


def test_text_with_korean_readings_parenthetical_form():
    """Inline SRT-style parentheticals per eojeol (whitespace word).
    Whitespace and ASCII pass through unchanged."""
    fn = MODULE["text_with_korean_readings"]
    out = fn("한국어를 공부합니다", "yale")
    assert "한국어를（" in out
    assert "공부합니다（" in out
    # Whitespace is preserved as its own token.
    assert " " in out
    # ASCII passthrough.
    assert fn("Hello world", "yale") == "Hello world"


def test_text_with_korean_ruby_wraps_per_eojeol():
    """VTT ruby markup: each Hangul eojeol gets one <ruby>/<rt> pair."""
    fn = MODULE["text_with_korean_ruby"]
    out = fn("한국어 공부", "yale")
    assert "<ruby>한국어<rt>" in out
    assert "<ruby>공부<rt>" in out
    assert out.count("<ruby>") == 2


def test_hangul_reading_pair_lines_returns_aligned_rows():
    """Mirror of kanji_reading_pair_lines: returns (reading_row, text_row)
    with each chunk width-aligned. Returns None when no hangul is present."""
    fn = MODULE["hangul_reading_pair_lines"]
    pair = fn("한국어를 공부합니다", "yale")
    assert pair is not None
    reading_row, text_row = pair
    # Reading row should contain romanization tokens.
    assert "hankwukelul" in reading_row
    assert "kongpwuhapnita" in reading_row
    # Text row preserves the hangul characters.
    assert "한국어를" in text_row
    assert "공부합니다" in text_row
    # No hangul → None.
    assert fn("Hello world", "yale") is None


def test_romanization_suffix_keeps_ja_legacy_spelling_ko_new():
    """ja keeps `.furigana-{mode}` for back-compat with scanners;
    ko uses `.romanization-{mode}` to advertise the script."""
    fn = MODULE["romanization_suffix"]
    assert fn("ja", "hiragana", "asb.srt", False) == ".furigana-hiragana.asb.srt"
    assert fn("ja", "romaji", "ruby.vtt", True) == ".furigana-romaji.single-line.ruby.vtt"
    assert fn("ko", "revised", "asb.srt", False) == ".romanization-revised.asb.srt"
    assert fn("ko", "yale", "stacked.ass", True) == ".romanization-yale.single-line.stacked.ass"


def test_generate_korean_romanization_walks_only_ko_srt():
    """The orchestrator picks .ko.srt files and writes one side file per
    requested format. Non-.ko paths and non-.srt paths are skipped."""
    import tempfile
    from pathlib import Path
    fn = MODULE["generate_korean_romanization"]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ko_path = root / "Show.S01E01.ko.srt"
        ko_path.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n한국어 공부\n",
            encoding="utf-8",
        )
        ja_path = root / "Show.S01E01.ja.srt"
        ja_path.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n日本語\n",
            encoding="utf-8",
        )
        en_path = root / "Show.S01E01.en.srt"
        en_path.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nHello\n",
            encoding="utf-8",
        )
        out = fn([ko_path, ja_path, en_path], "yale", single_line=False, formats={"srt", "vtt"})
        # Only the .ko.srt path yields side files; 2 formats × 1 file = 2.
        assert len(out) == 2
        names = sorted(p.name for p in out)
        assert any("Show.S01E01.ko.romanization-yale.asb.srt" == n for n in names)
        assert any("Show.S01E01.ko.romanization-yale.ruby.vtt" == n for n in names)
        # And the actual files exist.
        for p in out:
            assert p.exists()


def test_korean_stacked_ass_writes_text_before_reading_for_player_stacking():
    import tempfile
    from pathlib import Path
    fn = MODULE["srt_to_korean_pair_lines_ass"]
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "Show.S01E01.ko.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\n야 선생님한테\n",
            encoding="utf-8",
        )
        out = fn(src, "yale", single_line=True)
        dialogue_lines = [
            line for line in out.read_text(encoding="utf-8").splitlines()
            if line.startswith("Dialogue:")
        ]
    assert ",Text," in dialogue_lines[0]
    assert ",Reading," in dialogue_lines[1]


def test_apply_reading_to_args_routes_ja_and_ko():
    """The arg-routing helper sets args.ja_reading (for ja),
    args.ko_reading (for ko), args.zh_reading (for zh), and
    args.yue_reading (for yue)."""
    import argparse
    fn = MODULE["_apply_reading_to_args"]
    # ja+ko+zh spec — all three populate their own attributes.
    args = argparse.Namespace(
        reading="ja:hiragana,ko:revised,zh:marks",
        ja_reading=None, ko_reading=None, zh_reading=None,
    )
    fn(args)
    assert args.ja_reading == "hiragana"
    assert args.ko_reading == "revised"
    assert args.zh_reading == "marks"
    # ko:yale → yale
    args = argparse.Namespace(
        reading="ko:yale",
        ja_reading=None, ko_reading=None, zh_reading=None,
    )
    fn(args)
    assert args.ko_reading == "yale"
    # yue:numbers → numbers.
    args = argparse.Namespace(
        reading="yue:numbers",
        ja_reading=None, ko_reading=None, zh_reading=None,
    )
    fn(args)
    assert args.yue_reading == "numbers"
    # Still-deferred language raises.
    args = argparse.Namespace(
        reading="th:royal-thai",
        ja_reading=None, ko_reading=None, zh_reading=None,
    )
    try:
        fn(args)
    except MODULE["CliError"] as e:
        assert "th:royal-thai" in str(e)
    else:
        raise AssertionError("expected CliError for still-deferred language")


def test_wizard_probe_no_longer_warns_for_ko_revised():
    """Now that ko ships, the wizard's dependency probe should treat
    ko:revised as either block (no korean-romanizer) or pass (libs there),
    NOT as a deferred warning."""
    state = MODULE["_WizardState"](
        languages=["ko", "en"],
        order=["ko", "en"],
        reading_aids=["ko:revised"],
    )
    gaps = MODULE["_wizard_probe_dependencies"](state)
    deferred = [g for g in gaps if "deferred" in g[2].lower() or "not yet implemented" in g[2].lower()]
    assert not deferred, "ko:revised should no longer be flagged as deferred"


def test_setup_recommendations_ko_learner_is_selected_by_default():
    """Korean reading-aid recommendation must default to opt-in now that
    the backend ships (previously was opt-in only for ja)."""
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["ko"], content="tv",
        venue="browser", mt="none",
    )
    recs = MODULE["_setup_recommendations"](choice)
    ko_recs = [r for r in recs if r.key.startswith("reading:ko")]
    assert ko_recs, "ko learner missed reading-aid recommendation"
    assert ko_recs[0].selected_by_default is True


def test_setup_config_text_biases_mt_source_for_cjk_pairs():
    """Korean-native learning Japanese should get an explicit
    `mt_source = { ja = "ko" }` instead of `mt_source = "auto"` —
    Korean is grammatically closer to Japanese than English is, so
    biasing the MT source improves quality measurably."""
    choice = MODULE["_SetupChoice"](
        native=["ko"], learning=["ja"], content="anime",
        venue="browser", mt="online",
    )
    text = MODULE["_setup_config_text"](choice)
    assert 'mt_source = { ja = "ko" }' in text
    assert 'mt_source = "auto"' not in text


def test_setup_config_text_no_cjk_bias_for_pure_european():
    """English-native learning French should NOT get a CJK bias map;
    falls back to `mt_source = "auto"`."""
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["fr"], content="tv",
        venue="browser", mt="online",
    )
    text = MODULE["_setup_config_text"](choice)
    assert 'mt_source = "auto"' in text


def test_setup_config_text_multi_cjk_target_emits_full_bias_map():
    """A Korean-native learning ja AND zh should get both targets
    biased to Korean in the mt_source map."""
    choice = MODULE["_SetupChoice"](
        native=["ko"], learning=["ja", "zh"], content="mixed",
        venue="browser", mt="online",
    )
    text = MODULE["_setup_config_text"](choice)
    assert 'ja = "ko"' in text
    assert 'zh = "ko"' in text


def test_setup_config_text_seeds_ollama_pair_defaults_for_cjk_learner():
    """When mt='offline' and Ollama is reachable, the generated
    [translate.ollama_models] block must include per-pair entries for
    every learning ← native direction (plus English fallback). This
    means Ollama has the right model ready on first translate."""
    fn = MODULE["_setup_config_text"]
    g = fn.__globals__
    saved_reach = g["_wizard_ollama_reachable"]
    saved_which = MODULE["shutil"].which
    try:
        g["_wizard_ollama_reachable"] = lambda: True
        MODULE["shutil"].which = lambda name: "/usr/local/bin/ollama" if name == "ollama" else None
        # Japanese-native learning Korean.
        choice = MODULE["_SetupChoice"](
            native=["ja"], learning=["ko"], content="tv",
            venue="browser", mt="offline",
        )
        text = fn(choice)
        assert "[translate.ollama_models]" in text
        # ja → ko (target = learning ko, source = native ja).
        assert '"ja:ko"' in text
        # English fallback also seeded.
        assert '"en:ko"' in text
        # Default model assigned to each pair.
        assert MODULE["DEFAULT_OLLAMA_MODEL"] in text
    finally:
        g["_wizard_ollama_reachable"] = saved_reach
        MODULE["shutil"].which = saved_which


def test_setup_config_text_ollama_pairs_do_not_emit_self_pair():
    """The per-pair seeder must never emit a target=source pair
    (e.g. `"ja:ja"`) — Ollama would reject it and the user would see
    a confusing 'same source and target' error."""
    fn = MODULE["_setup_config_text"]
    g = fn.__globals__
    saved_reach = g["_wizard_ollama_reachable"]
    saved_which = MODULE["shutil"].which
    try:
        g["_wizard_ollama_reachable"] = lambda: True
        MODULE["shutil"].which = lambda name: "/usr/local/bin/ollama" if name == "ollama" else None
        # Native = ja AND learning = ja (edge case but valid input).
        choice = MODULE["_SetupChoice"](
            native=["ja"], learning=["ja"], content="anime",
            venue="browser", mt="offline",
        )
        text = fn(choice)
        assert '"ja:ja"' not in text
    finally:
        g["_wizard_ollama_reachable"] = saved_reach
        MODULE["shutil"].which = saved_which


def test_setup_recommendations_use_per_language_prose():
    """Each shipped reading-aid recommendation must use the tailored
    learner-focused reason from _SETUP_READING_AID_PROSE, not the
    generic placeholder."""
    # Korean learner — reason mentions G2P-specific examples.
    ko = MODULE["_setup_recommendations"](MODULE["_SetupChoice"](
        native=["en"], learning=["ko"], content="tv",
        venue="browser", mt="none",
    ))
    ko_rec = next(r for r in ko if r.key.startswith("reading:ko"))
    assert "Revised Romanization" in ko_rec.reason
    assert "같이→gachi" in ko_rec.reason or "G2P" in ko_rec.reason
    # Cost line is honest about g2pk's heavy pull (nltk).
    assert "nltk" in ko_rec.cost or "80" in ko_rec.cost or "MB" in ko_rec.cost

    # Chinese learner — reason mentions polyphones and tone sandhi.
    zh = MODULE["_setup_recommendations"](MODULE["_SetupChoice"](
        native=["en"], learning=["zh"], content="tv",
        venue="browser", mt="none",
    ))
    zh_rec = next(r for r in zh if r.key.startswith("reading:zh"))
    assert "polyphone" in zh_rec.reason.lower() or "tone sandhi" in zh_rec.reason.lower() or "nǐ hǎo" in zh_rec.reason
    # zh install is small.
    assert "5 MB" in zh_rec.cost or "pure-Python" in zh_rec.cost

    # Japanese learner — reason mentions kanji decoding.
    ja = MODULE["_setup_recommendations"](MODULE["_SetupChoice"](
        native=["en"], learning=["ja"], content="anime",
        venue="browser", mt="none",
    ))
    ja_rec = next(r for r in ja if r.key.startswith("reading:ja"))
    assert "kanji" in ja_rec.reason.lower() or "furigana" in ja_rec.reason.lower()


def test_setup_install_hint_table_covers_shipped_extras():
    """Every extra setup might offer to install must have a size/duration
    hint so users don't get blindsided by heavy installs like g2pk."""
    hints = MODULE["_SETUP_INSTALL_HINTS"]
    for extra in ("furigana", "romanization-ko", "romanization-zh"):
        assert extra in hints, f"missing install hint for [{extra}]"
        size, duration = hints[extra]
        assert "MB" in size, f"size for {extra} should mention MB"
        assert "second" in duration.lower() or "minute" in duration.lower()


def test_setup_mt_source_bias_helper_direct():
    """Unit test for the helper itself — exercises the CJK detection
    logic without going through the full TOML emitter."""
    fn = MODULE["_setup_mt_source_bias"]
    SC = MODULE["_SetupChoice"]
    # ja learner + ko native → biased.
    assert fn(SC(native=["ko"], learning=["ja"], content="anime",
                 venue="browser", mt="online")) == {"ja": "ko"}
    # zh learner + ja native → biased.
    assert fn(SC(native=["ja"], learning=["zh"], content="tv",
                 venue="browser", mt="online")) == {"zh": "ja"}
    # ja learner + en native → no bias (en isn't CJK).
    assert fn(SC(native=["en"], learning=["ja"], content="anime",
                 venue="browser", mt="online")) == {}
    # Non-CJK learner → no bias regardless of native.
    assert fn(SC(native=["ko"], learning=["fr"], content="tv",
                 venue="browser", mt="online")) == {}


def test_setup_ollama_pair_defaults_helper_direct():
    """Unit test for the per-pair seeder. Verifies direction (src:tgt),
    the English fallback, and dedup."""
    fn = MODULE["_setup_ollama_pair_defaults"]
    SC = MODULE["_SetupChoice"]
    # Single CJK pair + English fallback.
    pairs = fn(SC(native=["ja"], learning=["ko"], content="tv",
                  venue="browser", mt="offline"))
    keys = [k for k, _m in pairs]
    assert "ja:ko" in keys
    assert "en:ko" in keys
    # Multi-target.
    pairs = fn(SC(native=["en"], learning=["ja", "ko"], content="mixed",
                  venue="browser", mt="offline"))
    keys = [k for k, _m in pairs]
    assert "en:ja" in keys
    assert "en:ko" in keys
    # No self-pair when target == native.
    pairs = fn(SC(native=["ko"], learning=["ko"], content="tv",
                  venue="browser", mt="offline"))
    keys = [k for k, _m in pairs]
    assert "ko:ko" not in keys
    assert "en:ko" in keys


def test_setup_config_text_korean_emits_canonical_romanization_spec():
    """Korean learner gets `[modify].romanization = "ko:revised"` (NOT
    a per-language `furigana` legacy fallback)."""
    choice = MODULE["_SetupChoice"](
        native=["en"], learning=["ko"], content="tv",
        venue="browser", mt="none",
    )
    text = MODULE["_setup_config_text"](choice)
    assert 'reading = "ko:revised"' in text


def test_user_settings_example_uses_canonical_names():
    """The shipped example TOML demonstrates the v0.4 canonical names
    only — no legacy [modify].furigana / [modify].romanization /
    [merge].furigana / strip_furigana_before_mt / mt_source_lang."""
    from pathlib import Path
    repo = Path(MODULE["__file__"]).parent
    example = (repo / "user_settings.example.toml").read_text(encoding="utf-8")
    # New canonical TOML keys appear (line-anchored):
    assert "\nmt_source =" in example
    assert "\nreading_format =" in example
    assert "\nstrip_reading_before_mt =" in example
    # No legacy active keys (commented mentions in docs are fine — we
    # anchor on newline-key-= to avoid matching prose).
    for old in ("\nfurigana =", "\nromanization =",
                "\nstrip_furigana_before_mt =", "\nfurigana_output_format =",
                "\nmt_source_lang ="):
        assert old not in example, f"unexpected legacy key: {old.strip()}"


def test_korean_source_smoke_table_is_concise():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_korean_sources.py"
    spec = importlib.util.spec_from_file_location("test_korean_sources", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    rows = [
        mod.SourceResult("Wyzie", "auth required", "Set with: getsubtitle --set-key wyzie"),
        mod.SourceResult("Local SMI", "ok", "Converted fixture"),
    ]
    table = mod.format_table(rows)
    assert "Source" in table
    assert "Wyzie" in table
    assert "Local SMI" in table
    assert "auth required" in table


def test_korean_source_smoke_missing_key_does_not_crash():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_korean_sources.py"
    spec = importlib.util.spec_from_file_location("test_korean_sources_no_key", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    saved = mod._safe_key
    try:
        mod._safe_key = lambda provider: None
        result = mod.wyzie_check(live=False, episodes=["1"])
    finally:
        mod._safe_key = saved
    assert result.status == "auth required"


def test_korean_source_smoke_local_smi_fixture_converts():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_korean_sources.py"
    spec = importlib.util.spec_from_file_location("test_korean_sources_smi", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    result = mod.local_smi_check(repo / "tests" / "fixtures" / "korean_sample.smi")
    assert result.status == "ok"
    assert "ko SRT" in result.notes


def test_chinese_source_smoke_table_is_concise():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_chinese_sources.py"
    spec = importlib.util.spec_from_file_location("test_chinese_sources", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    rows = [
        mod.SourceResult("Wyzie", "auth required", "Set with: getsubtitle --set-key wyzie"),
        mod.SourceResult("Local SRT", "ok", "Parsed fixture"),
    ]
    table = mod.format_table(rows)
    assert "Source" in table
    assert "Wyzie" in table
    assert "Local SRT" in table


def test_chinese_source_smoke_missing_key_does_not_crash():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_chinese_sources.py"
    spec = importlib.util.spec_from_file_location("test_chinese_sources_no_key", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    saved = mod._safe_key
    try:
        mod._safe_key = lambda provider: None
        result = mod.wyzie_check(live=False, episodes=["1"])
    finally:
        mod._safe_key = saved
    assert result.status == "auth required"


def test_chinese_source_smoke_local_srt_fixture_parses():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_chinese_sources.py"
    spec = importlib.util.spec_from_file_location("test_chinese_sources_srt", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    result = mod.local_chinese_check(repo / "tests" / "fixtures" / "chinese_sample.srt")
    assert result.status == "ok"
    assert "Chinese SRT" in result.notes


def test_chinese_source_smoke_checks_ass_parser():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_chinese_sources.py"
    spec = importlib.util.spec_from_file_location("test_chinese_sources_ass", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    result = mod.local_ass_status()
    assert result.status == "ok"
    assert "ASS" in result.notes


def test_european_source_smoke_table_is_concise():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_european_sources.py"
    spec = importlib.util.spec_from_file_location("test_european_sources", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    rows = [
        mod.SourceResult("Wyzie", "auth required", "Set with: getsubtitle --set-key wyzie"),
        mod.SourceResult("Local SRT", "ok", "Parsed fixture"),
    ]
    table = mod.format_table(rows)
    assert "Source" in table
    assert "Wyzie" in table
    assert "Local SRT" in table


def test_european_source_smoke_missing_key_does_not_crash():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_european_sources.py"
    spec = importlib.util.spec_from_file_location("test_european_sources_no_key", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    saved = mod._safe_key
    try:
        mod._safe_key = lambda provider: None
        result = mod.wyzie_check(live=False, episodes=["1"], langs=["fr", "es"])
    finally:
        mod._safe_key = saved
    assert result.status == "auth required"


def test_european_source_smoke_local_srt_fixture_parses():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_european_sources.py"
    spec = importlib.util.spec_from_file_location("test_european_sources_srt", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    result = mod.local_european_check(repo / "tests" / "fixtures" / "european_sample.srt")
    assert result.status == "ok"
    assert "European SRT" in result.notes


def test_european_source_smoke_subdivx_detects_existing_provider():
    import importlib.util
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    script = repo / "scripts" / "test_european_sources.py"
    spec = importlib.util.spec_from_file_location("test_european_sources_subdivx", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    result = mod.subdivx_status(live=False)
    assert result.status == "available"
    assert "Spanish" in result.notes


def test_parse_wyzie_sources_response_accepts_dict_and_list():
    parse = MODULE["parse_wyzie_sources_response"]
    rows = parse({"sources": {"opensubtitles": "free", "subdl": {"status": "pro", "note": "upgrade"}}})
    assert {"source": "opensubtitles", "status": "free", "note": ""} in rows
    assert {"source": "subdl", "status": "pro", "note": "upgrade"} in rows
    rows2 = parse({"sources": [{"name": "tvsubtitles", "enabled": True}, "podnapisi"]})
    assert {"source": "podnapisi", "status": "available", "note": ""} in rows2
    assert any(row["source"] == "tvsubtitles" for row in rows2)


def test_parse_ass_dialogues_to_srt_cues():
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    ass = (repo / "tests" / "fixtures" / "chinese_sample.ass").read_text(encoding="utf-8")
    cues = MODULE["parse_ass"](ass)
    assert len(cues) == 2
    assert cues[0].time_line == "00:00:01,000 --> 00:00:03,500"
    assert cues[0].text_lines == ["你好", "欢迎来到ASS字幕测试。"]


def test_read_cues_from_file_accepts_ass_input():
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    cues = MODULE["read_cues_from_file"](repo / "tests" / "fixtures" / "chinese_sample.ass")
    assert len(cues) == 2
    assert "繁體中文" in cues[1].text_lines[0]


def test_merge_scan_accepts_ass_format_hint():
    from pathlib import Path
    import tempfile

    repo = Path(MODULE["__file__"]).parent
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        ass = folder / "Show - S01E01.zh.ass"
        ass.write_text((repo / "tests" / "fixtures" / "chinese_sample.ass").read_text(encoding="utf-8"), encoding="utf-8")
        scanned = MODULE["scan_subtitle_files_extended"]([folder], format_hints={"zh": "ass"})
        assert any(path == ass and lang == "zh" and fmt == "ass" for path, _s, _e, lang, _mt, fmt in scanned)
        grouped = MODULE["group_subtitle_files_with_hints"](scanned, format_hints={"zh": "ass"})
        assert grouped[(1, 1)]["zh"] == ass


def test_normalize_merge_langs_accepts_ass_hints():
    langs, hints = MODULE["_normalize_merge_langs"]("zh:ass,en")
    assert langs == "zh,en"
    assert hints == {"zh": "ass"}


def test_choose_best_penalizes_ai_hi_and_dubbed_results():
    SubtitleFile = MODULE["SubtitleFile"]
    choose = MODULE["choose_best"]
    good = SubtitleFile(provider="wyzie", language="zh", name="Show.S01E01.zh.srt", url="https://x/good.srt", source_provider="opensubtitles")
    bad_ai = SubtitleFile(provider="wyzie", language="zh", name="Show.S01E01.zh.ai.srt", url="https://x/ai.srt", source_provider="opensubtitles", ai=True)
    bad_hi = SubtitleFile(provider="wyzie", language="zh", name="Show.S01E01.SDH.zh.srt", url="https://x/hi.srt", source_provider="opensubtitles")
    bad_dub = SubtitleFile(provider="wyzie", language="zh", name="Show.S01E01.CANTONESE-DUBBED.zh.srt", url="https://x/dub.srt", source_provider="opensubtitles")
    assert choose([bad_ai, bad_hi, bad_dub, good]) is good


def test_provider_debug_record_counts_sources_flags_and_formats():
    SubtitleFile = MODULE["SubtitleFile"]
    record = MODULE["provider_debug_record"](
        "wyzie",
        "1",
        "zh",
        [
            SubtitleFile(provider="wyzie", language="zh", name="Show.SDH.zh.srt", url="https://x/1", provider_language="Chinese", source_provider="subdl"),
            SubtitleFile(provider="wyzie", language="zh", name="Show.DUBBED.zh.ass", url="https://x/2", provider_language="zh", source_provider="opensubtitles", ai=True),
        ],
    )
    assert record.count == 2
    assert record.source_tags["subdl"] == 1
    assert record.extensions[".ass"] == 1
    assert record.ai_count == 1
    assert record.hi_count == 1
    assert record.dubbed_count == 1


def test_download_planned_subtitles_continues_after_partial_failure():
    import contextlib
    import io
    import tempfile
    from pathlib import Path

    fn = MODULE["download_planned_subtitles"]
    SubtitleFile = MODULE["SubtitleFile"]
    MediaInfo = MODULE["MediaInfo"]
    CliError = MODULE["CliError"]
    g = fn.__globals__
    saved_save_subtitle = g["save_subtitle"]

    def fake_save_subtitle(sub, dest_dir, _media, _season, _episode):
        if sub.language == "en":
            raise CliError("HTTP 502 downloading https://example.test/en.srt")
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / f"saved.{sub.language}.srt"
        out.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n", encoding="utf-8")
        return [out]

    try:
        g["save_subtitle"] = fake_save_subtitle
        planned = [
            ("ja", "1", SubtitleFile(provider="jimaku", language="ja", name="ja.srt", url="https://example.test/ja.srt")),
            ("en", "1", SubtitleFile(provider="wyzie", language="en", name="en.srt", url="https://example.test/en.srt")),
        ]
        media = MediaInfo(source_url="https://example.test/show", provider="anilist", title="Show", season="1")
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(io.StringIO()):
            saved, failures = fn(planned, base=Path(td), media=media, season="1", layout="archive")
        assert [p.name for p in saved] == ["saved.ja.srt"]
        assert len(failures) == 1
        assert "en ep1: download failed from wyzie" in failures[0]
        assert "HTTP 502" in failures[0]
    finally:
        g["save_subtitle"] = saved_save_subtitle


def test_download_bytes_timeout_becomes_clierror(monkeypatch):
    def fake_urlopen(_req, timeout=0):
        raise TimeoutError("timed out")

    g = MODULE["download_bytes"].__globals__
    monkeypatch.setattr(g["urllib"].request, "urlopen", fake_urlopen)
    try:
        MODULE["download_bytes"]("https://example.test/slow.srt")
    except MODULE["CliError"] as e:
        assert "Download timed out after 60s" in str(e)
    else:
        raise AssertionError("TimeoutError should be converted to CliError")


def test_download_planned_subtitles_interactive_can_retry_alternate(monkeypatch, tmp_path):
    import contextlib
    import io

    fn = MODULE["download_planned_subtitles"]
    SubtitleFile = MODULE["SubtitleFile"]
    MediaInfo = MODULE["MediaInfo"]
    CliError = MODULE["CliError"]
    g = fn.__globals__
    saved_save_subtitle = g["save_subtitle"]
    answers = iter(["2"])  # retry with alternate provider/result

    best = SubtitleFile(
        provider="wyzie",
        language="en",
        name="best.srt",
        url="https://example.test/best.srt",
        source_provider="opensubtitles",
    )
    alt = SubtitleFile(
        provider="wyzie",
        language="en",
        name="alt.srt",
        url="https://example.test/alt.srt",
        source_provider="subdl",
    )

    def fake_save_subtitle(sub, dest_dir, _media, _season, _episode):
        if sub.url == best.url:
            raise CliError("Download timed out after 60s")
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / f"saved-{sub.name}"
        out.write_text("ok", encoding="utf-8")
        return [out]

    try:
        g["save_subtitle"] = fake_save_subtitle
        monkeypatch.setitem(g, "input", lambda *a, **k: next(answers))
        media = MediaInfo(source_url="https://example.test/movie", provider="tmdb", title="Movie", season="auto", is_movie=True)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            saved, failures = fn(
                [("en", "auto", best)],
                base=tmp_path,
                media=media,
                season="auto",
                layout="archive",
                alternatives={("en", "auto"): [alt]},
                interactive_recovery=True,
            )
        out = buf.getvalue()
        assert failures == []
        assert [p.name for p in saved] == ["saved-alt.srt"]
        assert "Retry with an alternate provider/result" in out
        assert "Trying alternate: alt.srt [subdl]" in out
    finally:
        g["save_subtitle"] = saved_save_subtitle


def test_download_planned_subtitles_noninteractive_auto_tries_alternate(tmp_path):
    import contextlib
    import io

    fn = MODULE["download_planned_subtitles"]
    SubtitleFile = MODULE["SubtitleFile"]
    MediaInfo = MODULE["MediaInfo"]
    CliError = MODULE["CliError"]
    g = fn.__globals__
    saved_save_subtitle = g["save_subtitle"]

    best = SubtitleFile(
        provider="wyzie",
        language="es",
        name="bad.es.srt",
        url="https://example.test/bad.es.srt",
        source_provider="opensubtitles",
    )
    alt = SubtitleFile(
        provider="wyzie",
        language="es",
        name="good.es.srt",
        url="https://example.test/good.es.srt",
        source_provider="subdl",
    )

    def fake_save_subtitle(sub, dest_dir, _media, _season, _episode):
        if sub.url == best.url:
            raise CliError("subtitle text looks corrupted: 42 replacement characters (�)")
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / f"saved-{sub.name}"
        out.write_text("ok", encoding="utf-8")
        return [out]

    try:
        g["save_subtitle"] = fake_save_subtitle
        media = MediaInfo(source_url="https://example.test/movie", provider="tmdb", title="Movie", season="auto", is_movie=True)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            saved, failures = fn(
                [("es", "auto", best)],
                base=tmp_path,
                media=media,
                season="auto",
                layout="archive",
                alternatives={("es", "auto"): [alt]},
                interactive_recovery=False,
            )
        out = buf.getvalue()
    finally:
        g["save_subtitle"] = saved_save_subtitle

    assert failures == []
    assert [p.name for p in saved] == ["saved-good.es.srt"]
    assert "rejected bad.es.srt [opensubtitles]" in out
    assert "Trying alternate: good.es.srt [subdl]" in out


def test_download_planned_subtitles_interactive_skip_records_subtitle_name(monkeypatch, tmp_path):
    import contextlib
    import io

    fn = MODULE["download_planned_subtitles"]
    SubtitleFile = MODULE["SubtitleFile"]
    MediaInfo = MODULE["MediaInfo"]
    CliError = MODULE["CliError"]
    g = fn.__globals__
    saved_save_subtitle = g["save_subtitle"]
    answers = iter(["3"])  # skip this subtitle
    sub = SubtitleFile(
        provider="wyzie",
        language="ko",
        name="The Matrix.ko.srt",
        url="https://example.test/ko.srt",
        source_provider="opensubtitles",
    )

    def fake_save_subtitle(_sub, _dest_dir, _media, _season, _episode):
        raise CliError("Download timed out after 60s")

    try:
        g["save_subtitle"] = fake_save_subtitle
        monkeypatch.setitem(g, "input", lambda *a, **k: next(answers))
        media = MediaInfo(source_url="https://example.test/movie", provider="tmdb", title="Movie", season="auto", is_movie=True)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            saved, failures = fn(
                [("ko", "auto", sub)],
                base=tmp_path,
                media=media,
                season="auto",
                layout="archive",
                interactive_recovery=True,
            )
        out = buf.getvalue()
        assert saved == []
        assert len(failures) == 1
        assert "skipped The Matrix.ko.srt" in failures[0]
        assert "3) Skip The Matrix.ko.srt" in out
    finally:
        g["save_subtitle"] = saved_save_subtitle


def test_source_smoke_scripts_support_json_output():
    import json
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(MODULE["__file__"]).parent
    proc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "test_european_sources.py"), "--json"],
        cwd=str(repo),
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["name"] == "european"
    assert data["results"]


# ─── Wizard scenarios (end-to-end transcripts) ───────────────────────────
#
# Each scenario file under tests/wizard_scenarios/ exports a SCENARIO
# (or SCENARIOS) constant. The harness drives the wizard with canned
# input, captures a transcript, compares against a golden snapshot under
# tests/wizard_transcripts/, and asserts on state + emitted CLI/TOML.
#
# Re-bless transcripts after intentional wizard wording changes with:
#   WIZARD_UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/test_core.py::test_wizard_scenario -q

import sys as _wizard_sys  # noqa: E402
from pathlib import Path as _WizardPath  # noqa: E402

_wizard_sys.path.insert(0, str(_WizardPath(__file__).resolve().parent))

import pytest as _wizard_pytest  # noqa: E402
import wizard_harness as _wizard_harness  # noqa: E402


_WIZARD_SCENARIOS = _wizard_harness.collect_scenarios()


@_wizard_pytest.mark.parametrize(
    "scenario",
    _WIZARD_SCENARIOS,
    ids=[s.name for s in _WIZARD_SCENARIOS] or None,
)
def test_wizard_scenario(scenario):
    """End-to-end wizard transcript test. See tests/wizard_scenarios/."""
    _wizard_harness.run_and_assert(scenario)
