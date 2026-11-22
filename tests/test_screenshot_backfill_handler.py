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
