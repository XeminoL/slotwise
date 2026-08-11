# %%
import csv
from collections import Counter, defaultdict

import matplotlib.pyplot as plt

from _common import (
    DATA,
    ACCENT,
    GOOD,
    style_fig,
    rows,
    parse_loc,
    kv,
    F_LOCATION,
    F_REFILL,
    F_STOCK,
    COL_AUTO_ID,
    COL_CREATED,
    COL_LOC_CODE,
    COL_LOC_ID,
    COL_QTY_IN,
    COL_QTY_OUT,
    COL_REFILL_TIME,
)

style_fig(plt)
DEAD_COLUMN_PCT = 5.0
CLEAN_DIR = DATA.parent / "data_clean"


def is_empty(v):
    v = (v or "").strip()
    if v == "" or v.upper() == "NULL":
        return True
    try:
        return float(v) == 0
    except ValueError:
        return False


# %%
def scan_files():
    files = sorted(DATA.glob("*.csv"))
    sizes = {}
    for f in files:
        with f.open(encoding="utf-8", errors="replace") as fh:
            header = fh.readline()
            ncol = header.count(",") + 1
            n = sum(1 for _ in fh)
        sizes[f.stem] = n
        kv(f.name, f"{n:>10,} rows" f"{ncol:>4} cols")


scan_files()


# %%
def scan_columns(path):
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        filled = [0] * len(header)
        total = 0
        for row in reader:
            total += 1
            for i, v in enumerate(row):
                if i < len(header) and not is_empty(v):
                    filled[i] += 1
    pct = [f / total * 100 if total else 0 for f in filled]
    return header, pct, total


def clean_file(path, out_path):
    header, pct, _ = scan_columns(path)
    keep = [i for i, p in enumerate(pct) if p >= DEAD_COLUMN_PCT]
    del_idx = next((i for i, h in enumerate(header) if h.strip().lower() == "deleted"), None)

    kept_rows = 0
    with path.open(encoding="utf-8", errors="replace", newline="") as fin, out_path.open(
        "w", encoding="utf-8", newline=""
    ) as fout:
        reader = csv.reader(fin)
        writer = csv.writer(fout)
        next(reader, None)
        writer.writerow([header[i] for i in keep])
        for row in reader:
            if del_idx is not None and del_idx < len(row) and row[del_idx].strip() == "1":
                continue
            writer.writerow([row[i] if i < len(row) else "" for i in keep])
            kept_rows += 1

    kv(path.name, f"{kept_rows:>10,} rows  {len(keep):>2} cols")


def clean_all():
    CLEAN_DIR.mkdir(exist_ok=True)
    for path in sorted(DATA.glob("*.csv")):
        clean_file(path, CLEAN_DIR / path.name)


clean_all()


# %%
def warehouse_shape():
    zone_aisles = defaultdict(set)
    n = 0
    for r in rows(F_LOCATION, main_warehouse_only=True):
        p = parse_loc(r[COL_LOC_CODE])
        if not p:
            continue
        n += 1
        zone_aisles[p["zone"]].add(p["aisle"])
    for z in sorted(zone_aisles, key=lambda z: -len(zone_aisles[z])):
        kv(f"zone {z}", f"{len(zone_aisles[z]):>3} aisles")
    kv("valid cells", f"{n:,}")


warehouse_shape()


# %%
def distributions():
    id2zone = {}
    for r in rows(F_LOCATION, main_warehouse_only=True):
        p = parse_loc(r[COL_LOC_CODE])
        if p:
            id2zone[r[COL_AUTO_ID]] = p["zone"]
    stock = Counter()
    for r in rows(F_STOCK):
        try:
            if float(r.get(COL_QTY_IN) or 0) - float(r.get(COL_QTY_OUT) or 0) > 0:
                z = id2zone.get(r.get(COL_LOC_ID))
                if z:
                    stock[z] += 1
        except ValueError:
            pass
    hour = Counter()
    total_repl = 0
    for r in rows(F_REFILL, done_only=True):
        total_repl += 1
        t = r.get(COL_REFILL_TIME) or r.get(COL_CREATED) or ""
        m = t[11:13] if len(t) >= 13 else None
        if m and m.isdigit():
            hour[int(m)] += 1
    for z, c in stock.most_common(5):
        kv(f"stock zone {z}", f"{c:,} cells")
    peak = max(hour, key=hour.get) if hour else 0
    kv("total replenishments", f"{total_repl:,}")

    _, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.8))
    zs = [z for z, _ in stock.most_common(6)]
    a1.bar(zs, [stock[z] for z in zs], color=ACCENT)
    a1.set_title("Stock by zone")
    hh = list(range(24))
    a2.bar(hh, [hour.get(h, 0) for h in hh], color=[GOOD if h == peak else ACCENT for h in hh])
    a2.set_title("Replenishment moves by hour")
    a2.set_xlabel("hour")


distributions()