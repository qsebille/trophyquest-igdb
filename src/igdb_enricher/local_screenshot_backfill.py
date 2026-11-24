import argparse
import json
import os

import dotenv
from requests import RequestException
from sqlalchemy import text

from igdb_enricher.backfill_screenshots import BATCH_SIZE, backfill_screenshots
from igdb_enricher.config.postgres import TrophyQuestPostgresConfig
from igdb_enricher.config.twitch import TwitchConfig
from igdb_enricher.screenshot_backfill_handler import _parse_event


def handler(event, context=None):
    game_ids, options = _parse_event(event)
    if os.environ.get("POSTGRES_HOST") not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("The local backfill requires a loopback PostgreSQL host")

    engine = TrophyQuestPostgresConfig().engine
    twitch = TwitchConfig()
    try:
        with engine.connect() as connection:
            baseline = dict(connection.execute(text("""
                WITH matched_games AS (
                    SELECT DISTINCT matched_game_id AS game_id
                    FROM app.igdb_matching
                    WHERE status IN ('AUTO_MATCH', 'MANUAL_MATCH')
                      AND matched_game_id IS NOT NULL
                )
                SELECT COUNT(*) AS matched_games,
                       COUNT(*) FILTER (WHERE g.game_id > :after_game_id) AS games_left_to_scan,
                       COUNT(*) FILTER (WHERE NOT EXISTS (
                           SELECT 1 FROM igdb.screenshot s WHERE s.game_id = g.game_id
                       )) AS games_without_screenshots
                FROM matched_games g
            """), {"after_game_id": options.get("after_game_id", 0)}).mappings().one())
        if game_ids:
            baseline.pop("games_left_to_scan")
        print(json.dumps({"stage": "start", **baseline}), flush=True)

        games_processed = 0
        screenshots_inserted = 0
        while True:
            page = backfill_screenshots(engine, twitch, game_ids, **options)
            games_processed += page["games_processed"]
            screenshots_inserted += page["screenshots_inserted"]
            print(json.dumps({
                "stage": "batch",
                **page,
                "total_games_processed": games_processed,
                "total_screenshots_inserted": screenshots_inserted,
                "games_left_to_scan": (
                    max(0, baseline["games_left_to_scan"] - games_processed) if not game_ids else None
                ),
            }), flush=True)
            cursor = page["next_after_game_id"]
            if cursor is None:
                return {"games_processed": games_processed, "screenshots_inserted": screenshots_inserted}
            options["after_game_id"] = cursor
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Run the screenshot backfill against local PostgreSQL.")
    parser.add_argument("--limit", type=int, default=BATCH_SIZE, help="Games per scan page")
    parser.add_argument("--after-game-id", type=int, default=0, help="Resume after this IGDB game ID")
    args = parser.parse_args()
    dotenv.load_dotenv()
    try:
        summary = handler({"mode": "scan", "limit": args.limit, "after_game_id": args.after_game_id})
    except RequestException as error:
        status = error.response.status_code if error.response is not None else None
        parser.exit(1, f"Twitch or IGDB request failed ({type(error).__name__}, HTTP status: {status}).\n")
    print(json.dumps({"stage": "done", **summary}), flush=True)


if __name__ == "__main__":
    main()
