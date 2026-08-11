import json

from config import (
    CACHE,
    COLUMNS,
    DATA_DIR,
    DELETED_FLAG,
    FILES,
    LOCATION_LOCKED,
    STATUS_DONE,
    WAREHOUSE_ID,
)

WAREHOUSE_DIR = CACHE / "current_warehouse"
CONFIG_FILE = WAREHOUSE_DIR / "schema.json"


ROLE_FILES = {
    "pick": "pick.csv",
    "refill_log": "refill_log.csv",
    "location": "location.csv",
    "stock": "stock.csv",
    "product": "product.csv",
}


SOURCE_FILES = dict(FILES)


DEFAULT_COLS = dict(COLUMNS)


DEFAULT_VALS = {
    "deleted_flag": DELETED_FLAG,
    "status_done": STATUS_DONE,
    "warehouse_id": WAREHOUSE_ID,
    "location_locked": LOCATION_LOCKED,
}

CONFIG_COLUMNS_KEY = "columns"
CONFIG_VALUES_KEY = "flags"

_config = None


def _load():
    global _config
    if _config is not None:
        return _config
    columns = dict(DEFAULT_COLS)
    values = dict(DEFAULT_VALS)
    uploaded_dir = None
    if CONFIG_FILE.exists():
        try:
            stored = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            columns.update(stored.get(CONFIG_COLUMNS_KEY) or {})
            values.update(stored.get(CONFIG_VALUES_KEY) or {})
            uploaded_dir = WAREHOUSE_DIR
        except (ValueError, OSError):
            pass
    _config = {"columns": columns, "values": values, "uploaded_dir": uploaded_dir}
    return _config


def col(role):
    return _load()["columns"].get(role, role)


def val(name):
    return _load()["values"][name]


def file_path(role):
    if _load()["uploaded_dir"] is not None:
        return WAREHOUSE_DIR / ROLE_FILES[role]
    return DATA_DIR / SOURCE_FILES[role]


def write_config(columns, values):
    global _config
    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(
            {CONFIG_COLUMNS_KEY: columns, CONFIG_VALUES_KEY: values},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    _config = None


def is_ready():
    if not CONFIG_FILE.exists():
        return False, list(ROLE_FILES)
    missing = [role for role, name in ROLE_FILES.items() if not (WAREHOUSE_DIR / name).exists()]
    return (not missing), missing