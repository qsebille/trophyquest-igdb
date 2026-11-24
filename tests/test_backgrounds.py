from unittest.mock import MagicMock, Mock

import pytest

from igdb_enricher import backfill
from igdb_enricher.config.twitch import TwitchConfig
from igdb_enricher.search_candidates.models.artwork import compute_candidate_background


def image(image_id, width=1280, height=720, image_type=None):
    return {"image_id": image_id, "width": width, "height": height, "image_type": image_type}


def test_prefers_logo_free_art_even_if_a_screenshot_is_closer_to_sixteen_nine():
    url = compute_candidate_background(
        [image(None, image_type=2), image("logo", image_type=3),
         image("art", 1920, 1200, {"id": 2})],
        [image("screen", 1920, 1080)],
    )

    assert url == "https://images.igdb.com/igdb/image/upload/t_720p/art.jpg"


def test_prefers_closer_ratio_then_larger_area_and_uses_a_stable_tie_break():
    artworks = [
        image("wider", 2560, 1080), image("small"), image("z", 1920, 1080), image("a", 1920, 1080),
    ]
    expected = "https://images.igdb.com/igdb/image/upload/t_720p/a.jpg"

    assert compute_candidate_background(artworks, []) == expected
    assert compute_candidate_background(artworks[::-1], []) == expected


def test_falls_back_to_a_screenshot_only_if_no_artwork_qualifies():
    artworks = [image("portrait", 1600, 2400), image("too-small", 1279, 720), image("bad-height", height=None)]

    assert compute_candidate_background(artworks, [image("screen")]).endswith("/screen.jpg")
    assert compute_candidate_background(artworks, [image(" "), image("square", 1280, 1280)]) is None


def test_scan_previews_only_current_page_and_distinguishes_unreturned_ids(monkeypatch):
    engine = MagicMock()
    reader = engine.connect.return_value.__enter__.return_value
    reader.execute.return_value.scalars.return_value.all.return_value = [1002, 1003, 1004, 1005]
    request_igdb = Mock(return_value=[{"id": 1002, "screenshots": [image("screen")]}, {"id": 1003}])
    monkeypatch.setattr(backfill, "request_igdb_games", request_igdb)

    request = backfill.parse_event({"operation": "backgrounds", "mode": "scan", "limit": 3, "after_game_id": 1001})
    result = backfill.run_backfill(engine, TwitchConfig(), request)

    assert result == {
        "operation": "backgrounds", "dry_run": True, "games_processed": 3, "games_recoverable": 1,
        "games_updated": 0, "games_without_candidate": 1, "missing_igdb_game_ids": [1004],
        "next_after_game_id": 1004,
        "proposals": [{
            "game_id": 1002, "background_url": "https://images.igdb.com/igdb/image/upload/t_720p/screen.jpg",
        }],
    }
    assert "where id = (1002, 1003, 1004); limit 3;" in request_igdb.call_args.args[0]
    assert reader.execute.call_args.args[0].compile().params == {"after_game_id": 1001, "fetch_limit": 4}
    engine.begin.assert_not_called()


def test_targeted_apply_uses_guarded_update_and_replay_skips_completed_game(monkeypatch):
    engine = MagicMock()
    reader = engine.connect.return_value.__enter__.return_value
    reader.execute.return_value.scalars.return_value.all.side_effect = [[1002], []]
    writer = engine.begin.return_value.__enter__.return_value
    writer.execute.return_value.rowcount = 1
    request_igdb = Mock(return_value=[{"id": 1002, "artworks": [image("art")]}])
    monkeypatch.setattr(backfill, "request_igdb_games", request_igdb)
    request = backfill.parse_event({"operation": "backgrounds", "game_ids": [1002, 1003], "dry_run": False})

    assert backfill.run_backfill(engine, TwitchConfig(), request)["games_updated"] == 1
    assert backfill.run_backfill(engine, TwitchConfig(), request)["games_updated"] == 0

    statement, proposals = writer.execute.call_args.args
    assert "AUTO_MATCH" in str(statement)
    assert "COALESCE(game.igdb_background_url" in str(statement)
    assert "COALESCE(game.aws_background_url" in str(statement)
    assert proposals == [{
        "game_id": 1002, "background_url": "https://images.igdb.com/igdb/image/upload/t_720p/art.jpg",
    }]
    engine.begin.assert_called_once()
    request_igdb.assert_called_once()


def test_igdb_failure_allows_retrying_the_same_cursor(monkeypatch):
    engine = MagicMock()
    reader = engine.connect.return_value.__enter__.return_value
    reader.execute.return_value.scalars.return_value.all.return_value = [1002]
    request_igdb = Mock(side_effect=[RuntimeError("IGDB unavailable"), []])
    monkeypatch.setattr(backfill, "request_igdb_games", request_igdb)
    request = backfill.parse_event({
        "operation": "backgrounds", "mode": "scan", "after_game_id": 1001, "dry_run": False,
    })

    with pytest.raises(RuntimeError, match="IGDB unavailable"):
        backfill.run_backfill(engine, TwitchConfig(), request)

    assert backfill.run_backfill(engine, TwitchConfig(), request)["missing_igdb_game_ids"] == [1002]
    assert request_igdb.call_args_list[0] == request_igdb.call_args_list[1]
    engine.begin.assert_not_called()
