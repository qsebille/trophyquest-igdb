import json
from unittest.mock import Mock

import pytest

from igdb_enricher import screenshot_backfill_handler as backfill


@pytest.mark.parametrize("event", [
    None, {}, {"game_ids": []}, {"game_ids": [True]}, {"game_ids": [0]},
    {"mode": "scan", "limit": 51}, {"mode": "scan", "after_game_id": -1},
    {"mode": "scan", "game_ids": [1]},
])
def test_invalid_invocations_do_not_access_secrets(monkeypatch, event):
    client = Mock()
    monkeypatch.setattr(backfill.boto3, "client", client)

    with pytest.raises(ValueError):
        backfill.handler(event, None)

    client.assert_not_called()


@pytest.mark.parametrize(("event", "expected"), [
    ({"game_ids": [2, 2, 3]}, ([2, 3], {})),
    ({"mode": "scan", "limit": 10, "after_game_id": 5}, ([], {"scan_limit": 10, "after_game_id": 5})),
])
def test_valid_invocation_selects_the_requested_scope(event, expected):
    assert backfill._parse_event(event) == expected


def test_handler_closes_secrets_manager_client_without_context_manager(monkeypatch):
    database = {"username": "user", "password": "password", "host": "localhost", "port": 5432, "dbname": "db"}
    twitch = {"client_id": "id", "client_secret": "secret"}
    client = Mock()
    client.get_secret_value.side_effect = [{"SecretString": json.dumps(value)} for value in (database, twitch)]
    engine = Mock()
    result = {"games_processed": 1, "screenshots_inserted": 2, "next_after_game_id": None}
    monkeypatch.setenv("POSTGRES_SECRET_ARN", "postgres")
    monkeypatch.setenv("TWITCH_SECRET_ARN", "twitch")
    monkeypatch.setattr(backfill.boto3, "client", Mock(return_value=client))
    monkeypatch.setattr(backfill, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(backfill, "backfill_screenshots", Mock(return_value=result))

    assert backfill.handler({"mode": "scan", "limit": 10}, None) == result
    client.close.assert_called_once_with()
    engine.dispose.assert_called_once_with()
