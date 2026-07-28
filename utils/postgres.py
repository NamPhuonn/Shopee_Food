from pathlib import Path

import psycopg2
import yaml


CONFIG_PATH = Path(__file__).resolve().parent / "config.yml"


def load_postgres_config(config_path: Path = CONFIG_PATH) -> dict:
    with open(config_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    postgres_config = data.get("postgres")
    if not postgres_config:
        raise KeyError(f"Missing 'postgres' section in config: {config_path}")

    return postgres_config


def get_postgres_connection(config_path: Path = CONFIG_PATH):
    config = load_postgres_config(config_path)
    return psycopg2.connect(
        host=config["host"],
        database=config["database"],
        user=config["user"],
        password=config["password"],
        port=config.get("port", 5432),
    )
