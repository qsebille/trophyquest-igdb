import json
from unittest.mock import Mock

import pytest

from igdb_enricher import backfill_handler
from igdb_enricher.backfill import BackfillRequest, parse_event


@pytest.mark.parametrize("event", [
    None,
    {},
    {"operation": ["backgrounds"], "mode": "scan"},
    {"operation": "screenshots", "mode": "scan"},
    {"operation": "backgrounds", "game_ids": []},
    {"operation": "backgrounds", "game_ids": [True]},
    {"operation": "backgrounds", "game_ids": [0]},
    {"operation": "backgrounds", "mode": "scan", "limit": 51},
    {"operation": "backgrounds", "mode": "scan", "after_game_id": -1},
    {"operation": "backgrounds", "mode": "scan", "game_ids": [1]},
    {"operation": "backgrounds", "mode": "scan", "dry_run": "false"},
])
def test_invalid_invocations_do_not_access_secrets(monkeypatch, event):
    client = Mock()
    monkeypatch.setattr(backfill_handler.boto3, "client", client)

    with pytest.raises(ValueError):
        backfill_handler.handler(event, None)

    client.assert_not_called()


@pytest.mark.parametrize(("event", "expected"), [
    ({"game_ids": [2, 2, 3]}, BackfillRequest("backgrounds", True, (2, 3))),
    ({"mode": "scan", "limit": 10, "after_game_id": 5, "dry_run": False},
     BackfillRequest("backgrounds", False, limit=10, after_game_id=5)),
])
def test_valid_invocation_selects_the_requested_scope(event, expected):
    assert parse_event({"operation": "backgrounds", **event}) == expected


def test_handler_defaults_to_preview_and_releases_resources(monkeypatch):
    database = {"username": "user", "password": "password", "host": "localhost", "port": 5432, "dbname": "db"}
    twitch = {"client_id": "id", "client_secret": "secret"}
    client = Mock()
    client.get_secret_value.side_effect = [{"SecretString": json.dumps(value)} for value in (database, twitch)]
    engine = Mock()
    run = Mock(return_value={"games_updated": 0, "next_after_game_id": None})
    monkeypatch.setenv("POSTGRES_SECRET_ARN", "postgres")
    monkeypatch.setenv("TWITCH_SECRET_ARN", "twitch")
    monkeypatch.setattr(backfill_handler.boto3, "client", Mock(return_value=client))
    monkeypatch.setattr(backfill_handler, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(backfill_handler, "run_backfill", run)

    assert backfill_handler.handler({"operation": "backgrounds", "mode": "scan", "limit": 10}, None) == run.return_value
    assert run.call_args.args[2] == BackfillRequest("backgrounds", True, limit=10)
    client.close.assert_called_once_with()
    engine.dispose.assert_called_once_with()
