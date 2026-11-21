from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from igdb_enricher import run
from igdb_enricher.backfill_screenshots import backfill_screenshots
from igdb_enricher.config.twitch import TwitchConfig
from igdb_enricher.search_candidates.models.candidate import IgdbCandidate


def test_enrichment_collects_screenshots_from_every_candidate(monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr(run, "TrophyQuestPostgresConfig", lambda: SimpleNamespace(engine=engine))
    monkeypatch.setattr(run, "search_unlinked_suites", lambda **_: [
        SimpleNamespace(id="suite-id", name="Game", platforms=["PS5"])
    ])
    candidates = [
        IgdbCandidate.from_dict({
            "id": game_id,
            "name": f"Game {game_id}",
            "game_type": {"type": "main_game"},
            "screenshots": [{"image_id": f"screen{game_id}"}],
        })
        for game_id in (1001, 1002)
    ]
    monkeypatch.setattr(run, "find_candidates", lambda **_: SimpleNamespace(all_candidates=candidates))
    monkeypatch.setattr(run, "rate_candidates", lambda **_: [])
    insert = Mock()
    monkeypatch.setattr(run, "insert_screenshots", insert)

    run.run_igdb_enricher(suite_limit=10)

    assert [(row.game_id, row.id) for row in insert.call_args.kwargs["rows"]] == [
        (1001, "screen1001"), (1002, "screen1002")
    ]


def test_backfill_inserts_only_screenshots_for_selected_matches(monkeypatch):
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalars.return_value.all.return_value = [1002]
    request = Mock(return_value=[{"id": 1002, "screenshots": [{"image_id": "screen1002"}]}])
    monkeypatch.setattr("igdb_enricher.backfill_screenshots.request_igdb_games", request)
    twitch = TwitchConfig()

    backfill_screenshots(engine, twitch, [1002, 1003])

    request.assert_called_once_with("fields id, screenshots.image_id; where id = (1002); limit 1;", twitch)
    write_connection = engine.begin.return_value.__enter__.return_value
    statement, rows = write_connection.execute.call_args.args
    assert "ON CONFLICT (id) DO NOTHING" in str(statement)
    assert rows == [{
        "id": "screen1002",
        "game_id": 1002,
        "igdb_url": "https://images.igdb.com/igdb/image/upload/t_720p/screen1002.jpg",
    }]
