import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CACHE
from data import warehouse as ck

OUT_FILE = CACHE / "heat_cache.json"
MAX_PICK_ROWS = 3_000_000


def _aisle_of_location():
    aisle = {}
    cols = (ck.col("auto_id"), ck.col("location_code"), ck.col("warehouse_id"),
            ck.col("status_id"), ck.col("deleted"))
    id_col, code_col, warehouse_col, status_col, del_col = cols
    locked, warehouse, deleted = ck.val("location_locked"), ck.val("warehouse_id"), ck.val("deleted_flag")
    with ck.file_path("location").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get(warehouse_col) != warehouse or row.get(del_col) == deleted:
                continue
            if row.get(status_col) == locked:
                continue
            m = re.match(r"^([A-Za-z]+\d+)", row.get(code_col) or "")
            if m:
                aisle[row[id_col]] = m.group(1)
    return aisle


def _count_picks(aisle_of):
    counts = Counter()
    loc_col = ck.col("location_id")
    with ck.file_path("pick").open(encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i >= MAX_PICK_ROWS:
                break
            a = aisle_of.get((row.get(loc_col) or "").strip())
            if a:
                counts[a] += 1
    return counts


def _count_refills(aisle_of):
    source, dest = Counter(), Counter()
    from_col = ck.col("location_code_from")
    to_col = ck.col("location_code_to")
    with ck.file_path("refill_log").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            for col, counter in ((from_col, source), (to_col, dest)):
                m = re.match(r"^([A-Za-z]+\d+)", (row.get(col) or "").strip())
                if m:
                    counter[m.group(1)] += 1
    return source, dest


def _to_ratio(counts):
    if not counts:
        return {}
    peak = max(counts.values())
    return {a: round(n / peak * 100, 1) for a, n in counts.items()}


def compute():
    aisle_of = _aisle_of_location()
    picks = _count_picks(aisle_of)
    source, dest = _count_refills(aisle_of)

    return {
        "pick": _to_ratio(picks),
        "refill_out": _to_ratio(source),
        "refill_in": _to_ratio(dest),
        "raw": {
            "pick": dict(picks.most_common()),
            "refill_out": dict(source.most_common()),
            "refill_in": dict(dest.most_common()),
        },
    }


def load(force=False):
    if OUT_FILE.exists() and not force:
        return json.loads(OUT_FILE.read_text(encoding="utf-8"))
    data = compute()
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


if __name__ == "__main__":
    try:
        d = load(force=True)
    except FileNotFoundError as err:
        raise SystemExit(f"Missing data file: {err.filename}. Upload the data through the web app first.")
    print(f"wrote {OUT_FILE.name}")
    for name in ("pick", "refill_out", "refill_in"):
        top = sorted(d["raw"][name].items(), key=lambda kv: -kv[1])[:5]
        total = sum(d["raw"][name].values())
        print(f"  {name:<12} {len(d['raw'][name]):>3} aisles, {total:>9,} moves")
        print(f"       top: {', '.join(f'{k}={v:,}' for k, v in top)}")
