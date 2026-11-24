from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from igdb_enricher import run
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
