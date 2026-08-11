import csv
import json
import re
from collections import Counter

from config import CACHE
from data import warehouse as ck

csv.field_size_limit(10**9)

CACHE_DASHBOARD = CACHE / "dashboard_cache.json"

ZONE_ORDER = ["A", "R", "P"]


def _model_stats():
    try:
        from core import brain as brain_mod

        brain = brain_mod.load()
        stats = (brain or {}).get("stats") or {}
        backtest = stats.get("backtest") or {}
        if not backtest.get("before"):
            return None
        return {
            "slotting_before": backtest["before"],
            "slotting_after": backtest["after"],
            "slotting_reduction": f"{backtest.get('reduction', 0)}%",
            "cluster_purity": stats.get("purity"),
        }
    except Exception:
        return None


def zone_of(code):
    m = re.match(r"^[A-Za-z]+", code or "")
    return m.group() if m else "?"


def _map_locations():
    c_del, c_code, c_id = ck.col("deleted"), ck.col("location_code"), ck.col("auto_id")
    v_del = ck.val("deleted_flag")
    code_of_id = {}
    cap_by_zone = Counter()
    total = 0
    with ck.file_path("location").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get(c_del) == v_del:
                continue
            code = row[c_code]
            code_of_id[row[c_id]] = code
            cap_by_zone[zone_of(code)] += 1
            total += 1
    return code_of_id, cap_by_zone, total


def _stock_by_zone(code_of_id):
    c_del, c_loc, c_in, c_out = (
        ck.col("deleted"),
        ck.col("location_id"),
        ck.col("qty_in"),
        ck.col("qty_out"),
    )
    v_del = ck.val("deleted_flag")
    occupied = {}
    with ck.file_path("stock").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get(c_del) == v_del:
                continue
            loc = row.get(c_loc) or ""
            code = code_of_id.get(loc)
            if not code:
                continue
            try:
                in_ = float(row.get(c_in) or 0)
                out_ = float(row.get(c_out) or 0)
            except ValueError:
                continue
            if in_ - out_ > 0:
                occupied.setdefault(zone_of(code), set()).add(loc)
    return Counter({z: len(s) for z, s in occupied.items()})


def compute():
    code_of_id, cap_by_zone, n_locations = _map_locations()
    stock = _stock_by_zone(code_of_id)

    zones = [z for z in ZONE_ORDER if z in cap_by_zone] + [
        z for z in sorted(cap_by_zone) if z not in ZONE_ORDER
    ]

    return {
        "model": _model_stats(),
        "warehouse": {
            "total_locations": n_locations,
            "zones": zones,
            "capacity_by_zone": {z: cap_by_zone[z] for z in zones},
            "stock_by_zone": {z: stock.get(z, 0) for z in zones},
        },
    }


def load(force=False):
    if CACHE_DASHBOARD.exists() and not force:
        return json.loads(CACHE_DASHBOARD.read_text(encoding="utf-8"))
    data = compute()
    CACHE_DASHBOARD.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


if __name__ == "__main__":
    d = load(force=True)
    print("model:", d["model"])
    print("total locations:", d["warehouse"]["total_locations"])
    print("zones:", d["warehouse"]["zones"])
    print("stock by zone:", d["warehouse"]["stock_by_zone"])