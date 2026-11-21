import argparse
import logging

import dotenv
from sqlalchemy import Engine, bindparam, text

from igdb_enricher.config.postgres import TrophyQuestPostgresConfig
from igdb_enricher.config.twitch import TwitchConfig
from igdb_enricher.search_candidates.igdb_request import request_igdb_games
from igdb_enricher.trophyquest.igdb_screenshot import IgdbScreenshotRow, insert_screenshots

BATCH_SIZE = 50


def backfill_screenshots(engine: Engine, twitch: TwitchConfig, game_ids: list[int]) -> None:
    query = """
        SELECT DISTINCT matched_game_id
        FROM app.igdb_matching
        WHERE status IN ('AUTO_MATCH', 'MANUAL_MATCH')
    """
    if game_ids:
        statement = text(query + " AND matched_game_id IN :game_ids ORDER BY matched_game_id").bindparams(
            bindparam("game_ids", value=game_ids, expanding=True)
        )
    else:
        statement = text(query + " ORDER BY matched_game_id")

    with engine.connect() as connection:
        matched_ids = connection.execute(statement).scalars().all()

    for start in range(0, len(matched_ids), BATCH_SIZE):
        batch = matched_ids[start:start + BATCH_SIZE]
        ids = ", ".join(str(game_id) for game_id in batch)
        games = request_igdb_games(
            f"fields id, screenshots.image_id; where id = ({ids}); limit {len(batch)};",
            twitch,
        )
        rows = [
            IgdbScreenshotRow.build(game["id"], screenshot["image_id"])
            for game in games
            for screenshot in game.get("screenshots", [])
            if screenshot.get("image_id")
        ]
        with engine.begin() as connection:
            insert_screenshots(connection, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill screenshots for matched TrophyQuest games.")
    parser.add_argument("game_ids", metavar="IGDB_GAME_ID", type=int, nargs="*",
                        help="IDs of matched games to backfill. Defaults to all matched games.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    dotenv.load_dotenv()
    engine = TrophyQuestPostgresConfig().engine
    try:
        backfill_screenshots(engine, TwitchConfig(), args.game_ids)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
