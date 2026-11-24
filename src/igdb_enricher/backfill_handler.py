import json
import logging
import os
from contextlib import closing

import boto3
from sqlalchemy import URL, create_engine

from igdb_enricher.backfill import parse_event, run_backfill
from igdb_enricher.config.twitch import TwitchConfig

logger = logging.getLogger(__name__)


def handler(event, context):
    request = parse_event(event)
    logging.getLogger().setLevel(logging.INFO)

    with closing(boto3.client("secretsmanager")) as client:
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
        result = run_backfill(
            engine,
            TwitchConfig(app_client_id=twitch["client_id"], app_client_secret=twitch["client_secret"]),
            request,
        )
        logger.info("IGDB backfill completed: %s", result)
        return result
    finally:
        engine.dispose()
