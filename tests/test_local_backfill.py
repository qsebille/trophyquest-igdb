import json
from unittest.mock import Mock

from igdb_enricher import local_backfill as local


def test_local_scan_follows_cursor_and_reports_progress(monkeypatch, capsys):
    engine = Mock()
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setattr(local, "TrophyQuestPostgresConfig", Mock(return_value=Mock(engine=engine)))
    backfill = Mock(side_effect=[
        {
            "games_processed": 2, "games_recoverable": 1, "games_updated": 0,
            "games_without_candidate": 1, "missing_igdb_game_ids": [], "next_after_game_id": 20,
        },
        {
            "games_processed": 1, "games_recoverable": 0, "games_updated": 0,
            "games_without_candidate": 0, "missing_igdb_game_ids": [30], "next_after_game_id": None,
        },
    ])
    monkeypatch.setattr(local, "run_backfill", backfill)

    result = local.run_local({"operation": "backgrounds", "mode": "scan", "limit": 2})

    assert result == {
        "games_processed": 3, "games_recoverable": 1, "games_updated": 0,
        "games_without_candidate": 1, "missing_igdb_game_ids": [30],
    }
    requests = [call.args[2] for call in backfill.call_args_list]
    assert [(request.after_game_id, request.dry_run) for request in requests] == [(0, True), (20, True)]
    progress = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [entry["next_after_game_id"] for entry in progress] == [20, None]
    engine.dispose.assert_called_once_with()
