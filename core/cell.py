import csv
import io
import json
import re
import sys
from collections import defaultdict

from config import CACHE
from data import warehouse as ck

csv.field_size_limit(10**9)

FILE_CACHE = CACHE / "cell_cache.json"

CELLS_PER_AISLE = 20
RESERVE_ZONE = "R"
PICK_ZONE = "A"
PALLET_ZONE = "P"
MAX_PRIORITY = 100


def floor_of(code):
    m = re.match(r"^[A-Za-z]+\d+-\d+-(\d+)$", code or "")
    return int(m.group(1)) if m else None


def aisle_of(code):
    m = re.match(r"^([A-Za-z]+\d+)-", code or "")
    return m.group(1) if m else None


def zone_of(code):
    m = re.match(r"^[A-Za-z]+", code or "")
    prefix = m.group() if m else "?"
    if prefix == PICK_ZONE:
        return PICK_ZONE
    for zone in (RESERVE_ZONE, PALLET_ZONE):
        if prefix.startswith(zone):
            return zone
    return prefix


def _cells_by_aisle():
    deleted_col, warehouse_col, code_col, id_col, type_col, status_col = (
        ck.col("deleted"),
        ck.col("warehouse_id"),
        ck.col("location_code"),
        ck.col("auto_id"),
        ck.col("location_type_id"),
        ck.col("status_id"),
    )
    deleted_flag, warehouse_id = ck.val("deleted_flag"), ck.val("warehouse_id")
    locked = ck.val("location_locked")
    by_id = {}
    by_aisle = defaultdict(list)
    with ck.file_path("location").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get(deleted_col) == deleted_flag or row.get(warehouse_col) != warehouse_id:
                continue
            if row.get(status_col) == locked:
                continue
            code = row[code_col]
            aisle = aisle_of(code)
            if not aisle:
                continue
            location_id = row[id_col]
            by_id[location_id] = (code, aisle, floor_of(code), row.get(type_col))
            by_aisle[aisle].append(location_id)
    return by_id, by_aisle


def _occupied_cells():
    deleted_col, location_col, received_col, issued_col = (
        ck.col("deleted"),
        ck.col("location_id"),
        ck.col("qty_in"),
        ck.col("qty_out"),
    )
    deleted_flag = ck.val("deleted_flag")
    occupied = set()
    with ck.file_path("stock").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get(deleted_col) == deleted_flag:
                continue
            location_id = row.get(location_col)
            try:
                received = float(row.get(received_col) or 0)
                issued = float(row.get(issued_col) or 0)
                if received - issued > 0:
                    occupied.add(location_id)
            except ValueError:
                pass
    return occupied


def compute():
    by_id, by_aisle = _cells_by_aisle()
    occupied = _occupied_cells()

    result = {}
    for aisle, location_ids in by_aisle.items():
        empties = []
        for location_id in location_ids:
            if location_id in occupied:
                continue
            code, _, floor, cell_type = by_id[location_id]
            empties.append(
                {"code": code, "floor": floor, "type": cell_type, "zone": zone_of(code)}
            )
        empties.sort(key=lambda c: (c["floor"] is None, c["floor"]))
        if empties:
            result[aisle] = _keep_every_floor(empties, CELLS_PER_AISLE)
    return result


def _keep_every_floor(empties, limit):
    """Trims the list but keeps at least one cell per floor, so floors stay selectable."""
    if len(empties) <= limit:
        return empties
    by_floor = defaultdict(list)
    for c in empties:
        by_floor[c["floor"]].append(c)
    kept = []
    while len(kept) < limit:
        added = False
        for floor in sorted(by_floor, key=lambda f: (f is None, f)):
            bucket = by_floor[floor]
            if bucket and len(kept) < limit:
                kept.append(bucket.pop(0))
                added = True
        if not added:
            break
    kept.sort(key=lambda c: (c["floor"] is None, c["floor"]))
    return kept


def load(force=False):
    if FILE_CACHE.exists() and not force:
        return json.loads(FILE_CACHE.read_text(encoding="utf-8"))
    data = compute()
    FILE_CACHE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


_TAKEN = set()
_OWNER = {}


def mark_taken(cell_code, owner=None):
    if not cell_code:
        return
    _TAKEN.add(cell_code)
    if owner is not None:
        _OWNER[cell_code] = owner


def release(owners):
    for code in [c for c, owner in _OWNER.items() if owner in owners]:
        _TAKEN.discard(code)
        del _OWNER[code]


def free_reserve_aisles(used=None):
    taken = (used or set()) | _TAKEN
    result = []
    for aisle, cells in load().items():
        if any(c.get("zone") == RESERVE_ZONE and c["code"] not in taken for c in cells):
            result.append(aisle)
    return result


def reset_session():
    _TAKEN.clear()
    _OWNER.clear()


def _target_floor(floors, speed_rank, heavy):
    priority = None
    if heavy is not None:
        priority = min(max(heavy, 0), 1) * MAX_PRIORITY
    elif speed_rank is not None:
        priority = min(max(speed_rank, 0), MAX_PRIORITY)
    if not floors or priority is None:
        return None
    height_ratio = 1 - priority / float(MAX_PRIORITY)
    index = min(int(height_ratio * len(floors)), len(floors) - 1)
    return floors[index]


def suggest_cell(aisle, used=None, speed_rank=None, heavy=None):
    empties = load().get(str(aisle))
    if not empties:
        return None
    taken = (used or set()) | _TAKEN
    free_reserve_cells = [
        c for c in empties if c.get("zone") == RESERVE_ZONE and c["code"] not in taken
    ]
    if not free_reserve_cells:
        return None

    floors = sorted({c["floor"] for c in free_reserve_cells if c["floor"] is not None})
    floor = _target_floor(floors, speed_rank, heavy)
    candidates = free_reserve_cells
    if floor is not None:
        candidates = [c for c in free_reserve_cells if c["floor"] == floor] or free_reserve_cells
    pick = candidates[0]
    return {
        "code": pick["code"],
        "floor": pick["floor"],
        "type": pick["type"],
        "zone": pick["zone"],
        "empties_in_aisle": max(0, len(free_reserve_cells)),
    }


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    data = load(force=True)
    print(f"aisles with free cells: {len(data)}")
    for aisle in list(data)[:3]:
        cell = suggest_cell(aisle)
        print(
            f"  aisle {aisle}: cell {cell['code']} (floor {cell['floor']}), "
            f"{cell['empties_in_aisle']} free"
        )