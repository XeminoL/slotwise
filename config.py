import json
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

DATA_DIR = Path(os.environ.get("SLOTWISE_DATA", ROOT_DIR / "data_in"))
CACHE = Path(os.environ.get("SLOTWISE_CACHE", ROOT_DIR / "cache"))

SCHEMA_FILE = Path(os.environ.get("SLOTWISE_SCHEMA", ROOT_DIR / "schema.json"))
SCHEMA_EXAMPLE = ROOT_DIR / "schema.example.json"

MIN_PICKS_TRUST = 20


def _read_schema():
    path = SCHEMA_FILE if SCHEMA_FILE.exists() else SCHEMA_EXAMPLE
    return json.loads(path.read_text(encoding="utf-8"))


SCHEMA = _read_schema()

COLUMNS = SCHEMA["columns"]
FILES = SCHEMA["files"]
FLAGS = SCHEMA["flags"]

WAREHOUSE_ID = FLAGS["warehouse_id"]
STATUS_DONE = FLAGS["status_done"]
LOCATION_LOCKED = FLAGS["location_locked"]
DELETED_FLAG = FLAGS["deleted"]
