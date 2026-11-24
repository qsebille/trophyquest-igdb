from sqlalchemy import Connection, text

from igdb_enricher.search_candidates.models.artwork import BACKGROUND_IMAGE_FIELDS, compute_candidate_background
from igdb_enricher.trophyquest.igdb_game import MISSING_BACKGROUND


MATCHED_GAME = """
    EXISTS (
        SELECT 1 FROM app.igdb_matching AS matching
        WHERE matching.matched_game_id = game.id
          AND matching.status IN ('AUTO_MATCH', 'MANUAL_MATCH')
    )
"""
ELIGIBLE_GAMES = f"""
    SELECT game.id FROM igdb.game AS game
    WHERE {MATCHED_GAME} AND {MISSING_BACKGROUND}
"""


def prepare(game: dict) -> dict | None:
    url = compute_candidate_background(game.get("artworks", []), game.get("screenshots", []))
    return {"game_id": game["id"], "background_url": url} if url else None


def write(connection: Connection, proposals: list[dict]) -> int:
    result = connection.execute(
        text(f"""
            UPDATE igdb.game AS game
            SET igdb_background_url = :background_url,
                aws_background_url = NULL
            WHERE game.id = :game_id AND {MATCHED_GAME} AND {MISSING_BACKGROUND}
        """),
        proposals,
    )
    return result.rowcount
