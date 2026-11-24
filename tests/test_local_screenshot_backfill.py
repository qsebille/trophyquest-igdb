import json
from unittest.mock import MagicMock, Mock

from igdb_enricher import local_screenshot_backfill as local


def test_local_scan_follows_cursor_and_reports_progress(monkeypatch, capsys):
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value.one.return_value = {
        "matched_games": 3,
        "games_without_screenshots": 2,
        "games_left_to_scan": 3,
    }
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setattr(local, "TrophyQuestPostgresConfig", Mock(return_value=Mock(engine=engine)))
    backfill = Mock(side_effect=[
        {"games_processed": 2, "screenshots_inserted": 4, "next_after_game_id": 20},
        {"games_processed": 1, "screenshots_inserted": 2, "next_after_game_id": None},
    ])
    monkeypatch.setattr(local, "backfill_screenshots", backfill)

    result = local.handler({"mode": "scan", "limit": 2})

    assert result == {"games_processed": 3, "screenshots_inserted": 6}
    assert [call.kwargs["after_game_id"] for call in backfill.call_args_list] == [0, 20]
    progress = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [entry["games_left_to_scan"] for entry in progress] == [3, 1, 0]
    engine.dispose.assert_called_once()
