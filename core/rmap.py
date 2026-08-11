import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict

from config import CACHE
from data import warehouse as ck

csv.field_size_limit(10**9)

CACHE_FILE = CACHE / "rmap_cache.json"
TOP_RESERVE = 5
RESERVE_ZONE = "R"
DEFAULT_DIST = 99
SPREAD_DECIMALS = 1
DIST_DECIMALS = 1


def _aisle_of(code):
    m = re.match(r"^([A-Za-z]+\d+)", code or "")
    return m.group(1) if m else None


def _aisle_num(aisle):
    m = re.search(r"\d+", aisle or "")
    return int(m.group()) if m else None


def _zone(aisle):
    m = re.match(r"^[A-Za-z]+", aisle or "")
    return m.group() if m else None


def _read_log():
    deleted_col, status_col = ck.col("deleted"), ck.col("status_id")
    source_col, dest_col = ck.col("location_code_from"), ck.col("location_code_to")
    deleted_flag, completed_status = ck.val("deleted_flag"), ck.val("status_done")
    sources_by_dest = defaultdict(Counter)
    dests_by_source = defaultdict(Counter)
    with ck.file_path("refill_log").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get(deleted_col) == deleted_flag or row.get(status_col) != completed_status:
                continue
            source = _aisle_of(row[source_col])
            dest = _aisle_of(row[dest_col])
            if source and dest:
                sources_by_dest[dest][source] += 1
                dests_by_source[source][dest] += 1
    return sources_by_dest, dests_by_source


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


def _standard_deviation(points, total):
    mean = sum(aisle_num * hits for aisle_num, hits in points) / total
    variance = sum(hits * (aisle_num - mean) ** 2 for aisle_num, hits in points) / total
    return variance**0.5


def _served_center(dests_by_source):
    center = {}
    spread = {}
    for reserve_aisle, dests in dests_by_source.items():
        if _zone(reserve_aisle) != RESERVE_ZONE:
            continue
        points = sorted(
            (_aisle_num(a), hits) for a, hits in dests.items() if _aisle_num(a) is not None
        )
        total = sum(hits for _, hits in points)
        if not total:
            continue
        center[reserve_aisle] = _weighted_median(points, total)
        spread[reserve_aisle] = _standard_deviation(points, total)
    return center, spread


def compute():
    sources_by_dest, dests_by_source = _read_log()
    center, spread = _served_center(dests_by_source)

    result = {}
    for dest, reserves in sources_by_dest.items():
        dest_num = _aisle_num(dest)
        total = sum(reserves.values())
        candidates = []
        for reserve_aisle, hits in reserves.items():
            if _zone(reserve_aisle) != RESERVE_ZONE or reserve_aisle not in center:
                continue
            distance = (
                abs(center[reserve_aisle] - dest_num) if dest_num is not None else DEFAULT_DIST
            )
            candidates.append(
                {
                    "aisle": reserve_aisle,
                    "share_pct": round(hits / total * 100),
                    "center": center[reserve_aisle],
                    "spread": round(spread.get(reserve_aisle, 0), SPREAD_DECIMALS),
                    "dist": round(distance, DIST_DECIMALS),
                }
            )

        candidates.sort(key=lambda c: (c["dist"], -c["share_pct"]))
        if candidates:
            result[dest] = candidates[:TOP_RESERVE]
    return result


def load(force=False):
    if CACHE_FILE.exists() and not force:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    data = compute()
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def storage_for(pick_aisle):
    return load().get(str(pick_aisle), [])


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    d = load(force=True)
    print(f"pick aisles mapped: {len(d)}")
    for k in list(d)[:5]:
        print(f"  {k} -> {d[k]}")