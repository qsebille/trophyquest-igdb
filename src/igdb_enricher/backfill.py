from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Connection, Engine, bindparam, text

from igdb_enricher import backfill_backgrounds
from igdb_enricher.config.twitch import TwitchConfig
from igdb_enricher.search_candidates.igdb_request import request_igdb_games


BATCH_SIZE = 50
_BIGINT_LIMIT = 2**63


@dataclass(frozen=True)
class BackfillOperation:
    eligible_games: str
    fields: str
    prepare: Callable[[dict], dict | None]
    write: Callable[[Connection, list[dict]], int]


OPERATIONS = {
    "backgrounds": BackfillOperation(
        backfill_backgrounds.ELIGIBLE_GAMES,
        backfill_backgrounds.BACKGROUND_IMAGE_FIELDS,
        backfill_backgrounds.prepare,
        backfill_backgrounds.write,
    ),
}


@dataclass(frozen=True)
class BackfillRequest:
    operation: str
    dry_run: bool
    game_ids: tuple[int, ...] = ()
    limit: int = BATCH_SIZE
    after_game_id: int = 0


def parse_event(event: dict) -> BackfillRequest:
    if not isinstance(event, dict):
        raise ValueError("Specify a supported backfill operation")

    operation = event.get("operation")
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ValueError("Specify a supported backfill operation")

    dry_run = event.get("dry_run", True)
    if type(dry_run) is not bool:
        raise ValueError("dry_run must be a boolean")

    shared_fields = {"operation", "dry_run"}
    if "game_ids" in event and event.keys() <= shared_fields | {"game_ids"}:
        game_ids = event["game_ids"]
        if (
            not isinstance(game_ids, list)
            or not 1 <= len(game_ids) <= BATCH_SIZE
            or not all(type(game_id) is int and 1 <= game_id < _BIGINT_LIMIT for game_id in game_ids)
        ):
            raise ValueError(f"game_ids must contain 1 to {BATCH_SIZE} positive integers")
        return BackfillRequest(operation, dry_run, tuple(dict.fromkeys(game_ids)))

    if event.get("mode") != "scan" or not event.keys() <= shared_fields | {"mode", "limit", "after_game_id"}:
        raise ValueError("Specify game_ids or explicitly request scan mode")

    limit = event.get("limit", BATCH_SIZE)
    after_game_id = event.get("after_game_id", 0)
    if type(limit) is not int or not 1 <= limit <= BATCH_SIZE:
        raise ValueError(f"limit must be between 1 and {BATCH_SIZE}")
    if type(after_game_id) is not int or not 0 <= after_game_id < _BIGINT_LIMIT:
        raise ValueError("after_game_id must be a non-negative bigint")
    return BackfillRequest(operation, dry_run, limit=limit, after_game_id=after_game_id)


def run_backfill(engine: Engine, twitch: TwitchConfig, request: BackfillRequest) -> dict:
    operation = OPERATIONS[request.operation]
    if request.game_ids:
        statement = text(f"""
            SELECT id FROM ({operation.eligible_games}) AS eligible
            WHERE id IN :game_ids ORDER BY id
        """).bindparams(bindparam("game_ids", value=request.game_ids, expanding=True))
    else:
        statement = text(f"""
            SELECT id FROM ({operation.eligible_games}) AS eligible
            WHERE id > :after_game_id ORDER BY id LIMIT :fetch_limit
        """).bindparams(after_game_id=request.after_game_id, fetch_limit=request.limit + 1)

    with engine.connect() as connection:
        eligible_ids = connection.execute(statement).scalars().all()

    game_ids = eligible_ids[:request.limit]
    next_after_game_id = game_ids[-1] if len(eligible_ids) > request.limit else None
    games = {}
    if game_ids:
        ids = ", ".join(str(game_id) for game_id in game_ids)
        games = {
            game["id"]: game
            for game in request_igdb_games(
                f"fields id, {operation.fields}; where id = ({ids}); limit {len(game_ids)};",
                twitch,
            )
        }

    proposals = []
    missing_game_ids = []
    without_candidate = 0
    for game_id in game_ids:
        if game_id not in games:
            missing_game_ids.append(game_id)
            continue
        proposal = operation.prepare(games[game_id])
        if proposal is None:
            without_candidate += 1
        else:
            proposals.append(proposal)

    updated = 0
    if not request.dry_run and proposals:
        with engine.begin() as connection:
            updated = operation.write(connection, proposals)

    return {
        "operation": request.operation,
        "dry_run": request.dry_run,
        "games_processed": len(game_ids),
        "games_recoverable": len(proposals),
        "games_updated": updated,
        "games_without_candidate": without_candidate,
        "missing_igdb_game_ids": missing_game_ids,
        "next_after_game_id": next_after_game_id,
        "proposals": proposals if request.dry_run else [],
    }
