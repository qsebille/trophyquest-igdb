from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

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
    write_connection = engine.begin.return_value.__enter__.return_value
    write_connection.execute.return_value.rowcount = 1
    request = Mock(return_value=[{"id": 1002, "screenshots": [{"image_id": "screen1002"}]}])
    monkeypatch.setattr("igdb_enricher.backfill_screenshots.request_igdb_games", request)
    twitch = TwitchConfig()

    result = backfill_screenshots(engine, twitch, [1002, 1003])

    assert result == {"games_processed": 1, "screenshots_inserted": 1, "next_after_game_id": None}
    request.assert_called_once_with("fields id, screenshots.image_id; where id = (1002); limit 1;", twitch)
    statement, rows = write_connection.execute.call_args.args
    assert "ON CONFLICT (id) DO NOTHING" in str(statement)
    assert rows == [{
        "id": "screen1002",
        "game_id": 1002,
        "igdb_url": "https://images.igdb.com/igdb/image/upload/t_720p/screen1002.jpg",
    }]


def test_scan_returns_cursor_and_replaying_the_page_does_not_insert_duplicates(monkeypatch):
    engine = MagicMock()
    reader = engine.connect.return_value.__enter__.return_value
    reader.execute.return_value.scalars.return_value.all.return_value = [1002, 1003]
    writer = engine.begin.return_value.__enter__.return_value
    writer.execute.side_effect = [SimpleNamespace(rowcount=1), SimpleNamespace(rowcount=0)]
    request = Mock(return_value=[{"id": 1002, "screenshots": [{"image_id": "screen1002"}]}])
    monkeypatch.setattr("igdb_enricher.backfill_screenshots.request_igdb_games", request)

    first = backfill_screenshots(engine, TwitchConfig(), [], scan_limit=1, after_game_id=1001)
    replay = backfill_screenshots(engine, TwitchConfig(), [], scan_limit=1, after_game_id=1001)

    statement = reader.execute.call_args.args[0]
    assert statement.compile().params == {"after_game_id": 1001, "fetch_limit": 2}
    assert first == {"games_processed": 1, "screenshots_inserted": 1, "next_after_game_id": 1002}
    assert replay == first | {"screenshots_inserted": 0}


def test_igdb_failure_allows_retrying_the_same_cursor(monkeypatch):
    engine = MagicMock()
    reader = engine.connect.return_value.__enter__.return_value
    reader.execute.return_value.scalars.return_value.all.return_value = [1002]
    request = Mock(side_effect=[RuntimeError("IGDB unavailable"), []])
    monkeypatch.setattr("igdb_enricher.backfill_screenshots.request_igdb_games", request)

    with pytest.raises(RuntimeError, match="IGDB unavailable"):
        backfill_screenshots(engine, TwitchConfig(), [], scan_limit=1, after_game_id=1001)

    engine.begin.assert_not_called()
    result = backfill_screenshots(engine, TwitchConfig(), [], scan_limit=1, after_game_id=1001)
    assert result == {"games_processed": 1, "screenshots_inserted": 0, "next_after_game_id": None}
