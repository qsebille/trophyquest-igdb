import argparse
import json
import os
from dataclasses import replace

import dotenv
from requests import RequestException

from igdb_enricher.backfill import BATCH_SIZE, OPERATIONS, parse_event, run_backfill
from igdb_enricher.config.postgres import TrophyQuestPostgresConfig
from igdb_enricher.config.twitch import TwitchConfig


def run_local(event: dict) -> dict:
    request = parse_event(event)
    if os.environ.get("POSTGRES_HOST") not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("The local backfill requires a loopback PostgreSQL host")

    engine = TrophyQuestPostgresConfig().engine
    twitch = TwitchConfig()
    counts = dict.fromkeys(("games_processed", "games_recoverable", "games_updated", "games_without_candidate"), 0)
    missing_igdb_game_ids = []
    try:
        while True:
            page = run_backfill(engine, twitch, request)
            for key in counts:
                counts[key] += page[key]
            missing_igdb_game_ids.extend(page["missing_igdb_game_ids"])
            print(json.dumps({"stage": "batch", **page}), flush=True)
            cursor = page["next_after_game_id"]
            if cursor is None:
                return {**counts, "missing_igdb_game_ids": missing_igdb_game_ids}
            request = replace(request, after_game_id=cursor)
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an IGDB backfill against local PostgreSQL.")
    parser.add_argument("operation", choices=OPERATIONS)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--game-ids", type=int, nargs="+", help="Process specific IGDB game IDs")
    scope.add_argument("--scan", action="store_true", help="Scan eligible games in batches")
    parser.add_argument("--limit", type=int, help=f"Games per scan page (default: {BATCH_SIZE})")
    parser.add_argument("--after-game-id", type=int, help="Resume a scan after this IGDB game ID")
    parser.add_argument("--apply", action="store_true", help="Write changes instead of previewing them")
    args = parser.parse_args()

    event = {"operation": args.operation, "dry_run": not args.apply}
    if args.scan:
        event["mode"] = "scan"
        if args.limit is not None:
            event["limit"] = args.limit
        if args.after_game_id is not None:
            event["after_game_id"] = args.after_game_id
    else:
        if args.limit is not None or args.after_game_id is not None:
            parser.error("--limit and --after-game-id require --scan")
        event["game_ids"] = args.game_ids

    dotenv.load_dotenv()
    try:
        summary = run_local(event)
    except ValueError as error:
        parser.error(str(error))
    except RequestException as error:
        status = error.response.status_code if error.response is not None else None
        parser.exit(1, f"Twitch or IGDB request failed ({type(error).__name__}, HTTP status: {status}).\n")
    print(json.dumps({"stage": "done", **summary}), flush=True)


if __name__ == "__main__":
    main()
