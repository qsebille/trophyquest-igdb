import json
import logging
import os

import boto3
from sqlalchemy import URL, create_engine

from igdb_enricher.backfill_screenshots import BATCH_SIZE, backfill_screenshots
from igdb_enricher.config.twitch import TwitchConfig

logger = logging.getLogger(__name__)


def _parse_event(event: dict) -> tuple[list[int], dict]:
    if isinstance(event, dict) and event.keys() == {"game_ids"}:
        ids = event["game_ids"]
        if (
            isinstance(ids, list)
            and 1 <= len(ids) <= BATCH_SIZE
            and all(type(game_id) is int and 1 <= game_id < 2**63 for game_id in ids)
        ):
            return list(dict.fromkeys(ids)), {}
        raise ValueError(f"game_ids must contain 1 to {BATCH_SIZE} positive integers")

    if (
        isinstance(event, dict)
        and event.get("mode") == "scan"
        and event.keys() <= {"mode", "limit", "after_game_id"}
    ):
        limit = event.get("limit", BATCH_SIZE)
        after_game_id = event.get("after_game_id", 0)
        if type(limit) is not int or not 1 <= limit <= BATCH_SIZE:
            raise ValueError(f"limit must be between 1 and {BATCH_SIZE}")
        if type(after_game_id) is not int or not 0 <= after_game_id < 2**63:
            raise ValueError("after_game_id must be a non-negative integer")
        return [], {"scan_limit": limit, "after_game_id": after_game_id}

    raise ValueError("Specify game_ids or explicitly request scan mode")


def handler(event, context):
    game_ids, options = _parse_event(event)
    logging.getLogger().setLevel(logging.INFO)

    with boto3.client("secretsmanager") as client:
        database = json.loads(client.get_secret_value(SecretId=os.environ["POSTGRES_SECRET_ARN"])["SecretString"])
        twitch = json.loads(client.get_secret_value(SecretId=os.environ["TWITCH_SECRET_ARN"])["SecretString"])

    engine = create_engine(
        URL.create(
            "postgresql+psycopg2",
            username=database["username"],
            password=database["password"],
            host=database["host"],
            port=int(database["port"]),
            database=database["dbname"],
        ),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    try:
        result = backfill_screenshots(
            engine,
            TwitchConfig(app_client_id=twitch["client_id"], app_client_secret=twitch["client_secret"]),
            game_ids,
            **options,
        )
        logger.info("Screenshot backfill completed: %s", result)
        return result
    finally:
        engine.dispose()
