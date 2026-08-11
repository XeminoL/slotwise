import csv
import io
import os
import re
import sys
from pathlib import Path

csv.field_size_limit(10**9)


if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DATA = Path(os.environ.get("SLOTWISE_DATA", Path(__file__).resolve().parent.parent / "data_in"))


MAIN_WAREHOUSE = os.environ.get("SLOTWISE_WAREHOUSE", "1")

COL_WAREHOUSE = os.environ.get("COL_WAREHOUSE", "warehouse_id")
COL_DELETED = os.environ.get("COL_DELETED", "deleted")
COL_STATUS = os.environ.get("COL_STATUS", "status_id")

F_PICK = os.environ.get("F_PICK", "pick_history.csv")
F_LOCATION = os.environ.get("F_LOCATION", "locations.csv")
F_STOCK = os.environ.get("F_STOCK", "stock.csv")
F_PRODUCT = os.environ.get("F_PRODUCT", "products.csv")
F_REFILL = os.environ.get("F_REFILL", "refill_log.csv")

COL_ORDER = os.environ.get("COL_ORDER", "order_id")
COL_ITEM = os.environ.get("COL_ITEM", "product_id")
COL_LOC_CODE = os.environ.get("COL_LOC_CODE", "location_code")
COL_LOC_FROM = os.environ.get("COL_LOC_FROM", "location_code_from")
COL_LOC_TO = os.environ.get("COL_LOC_TO", "location_code_to")
COL_LOC_ID = os.environ.get("COL_LOC_ID", "location_id")
COL_AUTO_ID = os.environ.get("COL_AUTO_ID", "auto_id")
COL_QTY_IN = os.environ.get("COL_QTY_IN", "qty_in")
COL_QTY_OUT = os.environ.get("COL_QTY_OUT", "qty_out")
COL_REFILL_TIME = os.environ.get("COL_REFILL_TIME", "refill_time")
COL_CREATED = os.environ.get("COL_CREATED", "created")
DONE_STATUS = os.environ.get("SLOTWISE_STATUS_DONE", "1")
DELETED_FLAG = os.environ.get("SLOTWISE_DELETED", "1")


BG = "#FFFFFF"
PANEL = "#FFFFFF"
INK = "#1A1A1A"
DIM = "#555555"
ACCENT = "#1F6FB2"
GOOD = "#2E8B57"
BAD = "#C0392B"
GRID = "#D9D9D9"


def style_fig(plt):
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#888888",
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": DIM,
            "ytick.color": DIM,
            "grid.color": GRID,
            "grid.linestyle": "--",
            "grid.linewidth": 0.6,
            "font.size": 10,
            "axes.titlecolor": INK,
            "axes.grid": True,
            "axes.axisbelow": True,
            "figure.dpi": 110,
            "savefig.facecolor": "white",
            "savefig.bbox": "tight",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def parse_loc(code):
    m = re.match(r"^([A-Za-z]+)(\d+)-(\d+)-(\d+)$", code or "")
    if not m:
        return None
    prefix = m.group(1)
    zone_map = {"A": "A", "R": "R", "P": "P"}
    zone = zone_map.get(prefix[0], prefix)
    return {
        "zone": zone,
        "aisle": prefix + m.group(2),
        "aisle_num": int(m.group(2)),
        "seq": int(m.group(3)),
        "floor": int(m.group(4)),
    }


def rows(filename, main_warehouse_only=False, done_only=False):
    path = DATA / filename
    try:
        with path.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get(COL_DELETED) == DELETED_FLAG:
                    continue
                if main_warehouse_only and r.get(COL_WAREHOUSE) != MAIN_WAREHOUSE:
                    continue
                if done_only and r.get(COL_STATUS) != DONE_STATUS:
                    continue
                yield r
    except FileNotFoundError:
        print(f"File not found: {path}")
        return
        yield

def kv(label, value, note=""):
    tail = f"  ({note})" if note else ""
    print(f"  {label}: {value}{tail}", flush=True)