import bisect
import csv
import io
import json
import sys

from config import CACHE
from data import warehouse as ck

csv.field_size_limit(10**9)

FILE_CACHE = CACHE / "weight_cache.json"

GRAMS_DECIMALS = 2


def compute():
    id_col, gross_weight_col = ck.col("auto_id"), ck.col("gross_weight")
    table = {}
    with ck.file_path("product").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            auto_id = row.get(id_col)
            try:
                gross_weight = float(row.get(gross_weight_col) or 0)
            except ValueError:
                gross_weight = 0
            if auto_id and gross_weight > 0:
                table[auto_id] = round(gross_weight, GRAMS_DECIMALS)
    return table


_WEIGHTS = None
_SORTED = None


def _rebuild_cache():
    global _WEIGHTS, _SORTED
    _WEIGHTS = compute()
    FILE_CACHE.write_text(json.dumps(_WEIGHTS), encoding="utf-8")
    _SORTED = sorted(_WEIGHTS.values()) or [0]


def _ensure():
    global _WEIGHTS, _SORTED
    if _WEIGHTS is not None:
        return
    if not FILE_CACHE.exists():
        _rebuild_cache()
        return
    _WEIGHTS = json.loads(FILE_CACHE.read_text(encoding="utf-8"))
    _SORTED = sorted(_WEIGHTS.values()) or [0]


def heavy(auto_id):
    _ensure()
    gross_weight = _WEIGHTS.get(str(auto_id))
    if gross_weight is None:
        return None
    rank = bisect.bisect_right(_SORTED, gross_weight)
    return rank / len(_SORTED)


def load(force=False):
    if force or not FILE_CACHE.exists():
        _rebuild_cache()
    else:
        _ensure()
    return _WEIGHTS


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    table = load(force=True)
    print(f"items with weight: {len(table)}")
    for auto_id in list(table)[:4]:
        print(f"  {auto_id}: {table[auto_id]}kg -> heavy {heavy(auto_id):.2f}")