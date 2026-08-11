import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict

from config import CACHE, MIN_PICKS_TRUST
from data import warehouse as ck

csv.field_size_limit(10**9)

CACHE_FILE = CACHE / "refill_cache.json"
TOP_DAY = 6
PICK_ZONE = "A"
SPREAD_DECIMALS = 1


def _zone_aisle(code):
    m = re.match(r"^([A-Za-z]+)(\d+)", code or "")
    return (m.group(1), int(m.group(2))) if m else (None, None)


def _weighted_median(points, total):
    median = points[-1][0]
    cumulative = 0
    for index, (aisle_num, hits) in enumerate(points):
        cumulative += hits
        if cumulative < total / 2:
            continue
        median = aisle_num
        tied_at_midpoint = cumulative == total / 2 and index + 1 < len(points)
        if tied_at_midpoint and points[index + 1][1] > hits:
            median = points[index + 1][0]
        break
    return median


def _spread(points, total):
    mean = sum(aisle_num * hits for aisle_num, hits in points) / total
    variance = sum(hits * (aisle_num - mean) ** 2 for aisle_num, hits in points) / total
    return variance**0.5


def _count_refill_hits_by_item():
    deleted_col, status_col, item_col, dest_col = (
        ck.col("deleted"),
        ck.col("status_id"),
        ck.col("product_id"),
        ck.col("location_code_to"),
    )
    deleted_flag, completed_status = ck.val("deleted_flag"), ck.val("status_done")
    hits_by_item = defaultdict(Counter)
    with ck.file_path("refill_log").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get(deleted_col) == deleted_flag or row.get(status_col) != completed_status:
                continue
            item = row.get(item_col)
            zone, aisle_num = _zone_aisle(row.get(dest_col))
            if item and zone == PICK_ZONE and aisle_num is not None:
                hits_by_item[item][aisle_num] += 1
    return hits_by_item


def compute():
    result = {}
    for item, hits_by_aisle in _count_refill_hits_by_item().items():
        total = sum(hits_by_aisle.values())
        if total < MIN_PICKS_TRUST:
            continue
        points = sorted(hits_by_aisle.items())
        days = [
            {"aisle": f"{PICK_ZONE}{aisle_num:02d}", "pct": round(hits / total * 100)}
            for aisle_num, hits in hits_by_aisle.most_common(TOP_DAY)
        ]
        result[item] = {
            "center": _weighted_median(points, total),
            "spread": round(_spread(points, total), SPREAD_DECIMALS),
            "days": days,
        }
    return result


def load(force=False):
    if CACHE_FILE.exists() and not force:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    data = compute()
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def for_item(item_id):
    return load().get(str(item_id))


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    data = load(force=True)
    print(f"items with history: {len(data)}")
    for item in list(data)[:4]:
        d = data[item]
        print(
            f"  {item}: center A{d['center']}, spread {d['spread']}, "
            + ", ".join(f"{x['aisle']}({x['pct']}%)" for x in d["days"][:4])
        )