import csv
import io
import re
from collections import Counter, defaultdict

from config import SCHEMA

csv.field_size_limit(10**9)

LOCATION_CODE = re.compile(r"^[A-Z]{1,4}\d+-\d+-\d+$")
PICK_AISLE_PREFIX = "A"
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")
SAMPLE_ROWS = 400

DELIMITERS = (",", ";", "\t", "|")
ENCODINGS = ("utf-8-sig", "utf-8", "cp1258", "cp1252", "latin-1")
SNIFF_BYTES = 8000
LOG_EVERY = 500_000


ID_MIN = 0.6
FILLED_MIN = 0.5
LOC_SHAPE_MIN = 0.5
NAME_SHAPE_MIN = 0.5
ALPHA_MIN = 0.5

LOC_FILE_SHAPE_MIN = 0.4
LOC_COLUMN_SHAPE_MIN = 0.3
LOC_WITH_CAPACITY_SHAPE_MIN = 0.2
PRODUCT_ID_SHAPE_MIN = 0.7
ORDER_REPEAT_MIN = 0.3
ORDER_REPEAT_MAX = 0.95
ITEM_REPEAT_MAX = 0.5
ORDER_DISTINCT_FLOOR = 10
ORDER_DISTINCT_SHARE = 0.15
DELETED_FLAG = "1"
MIN_TABLE_COLUMNS = 2
MIN_ITEMS_PER_MULTI_ORDER = 2
HEADER_NORMALIZE = re.compile(r"[\s_\-.]")
ID_TOKEN = re.compile(r"[A-Za-z0-9]{1,20}")
NON_ASCII = re.compile(r"[^\x00-\x7f]")
HAS_LETTER = re.compile(r"[A-Za-z]")
WORDY_LENGTH = 12
HEAD_LINES_FOR_SNIFF = 20
BOM = "﻿"

ORDER_HINT_WEIGHT = 3
ORDER_REPEAT_WEIGHT = 2
ITEM_HINT_WEIGHT = 3


ORDER_HINTS = ("orderid", "madon", "donhang", "phieupick", "sohd", "sodon")
ITEM_HINTS = ("sanphamid", "productid", "masanpham", "masp", "product", "item", "sku", "sanpham")

QUANTITY_HINTS = (
    "soluong",
    "slpick",
    "quantity",
    "qty",
    "sl",
    "amount",
    "gia",
    "price",
    "gw",
    "nw",
    "cbm",
    "weight",
    "khoiluong",
    "dongia",
)
LOC_HINTS = ("vitriid", "locationid", "vitri", "location", "masovitri", "vitri")
NAME_HINTS = ("tensanpham", "productname", "ten", "name", "mota")
CAT_HINTS = ("categoryid", "category", "nganhhang", "nganh", "loai")
CAP_HINTS = ("capacity", "succhua", "slpallet", "sopallet")

ORDER_HEADERS = ("orderid", "madon", "phieupick")
ITEM_HEADERS = ("sanphamid", "productid", "masanpham")
LOCATION_CODE_HEADERS = ("locationcode", "malocation", "masovitri")
PRODUCT_NAME_HEADERS = ("tensanpham", "productname")
PRODUCT_CODE_HEADERS = ("masanpham", "productcode", "masp")


class LoadError(Exception):
    pass


def _norm(header):
    return HEADER_NORMALIZE.sub("", (header or "").strip().lower())


def _decode(raw):
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _sniff_delimiter(text_head):
    head_lines = "\n".join(text_head.splitlines()[:HEAD_LINES_FOR_SNIFF])
    counts = {delimiter: head_lines.count(delimiter) for delimiter in DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _dedup_headers(headers):
    seen = Counter()
    unique = []
    for header in headers:
        key = f"{header}__{seen[header]}" if seen[header] else header
        seen[header] += 1
        unique.append(key)
    return unique


def read_table(raw):
    text = _decode(bytes(raw)) if isinstance(raw, (bytes, bytearray)) else raw
    text = text.lstrip(BOM)
    if not text.strip():
        raise LoadError("Empty file, no data.")

    delimiter = _sniff_delimiter(text[:SNIFF_BYTES])
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        headers = next(reader)
    except StopIteration:
        raise LoadError("Empty file, no data.")
    if len(headers) < MIN_TABLE_COLUMNS:
        raise LoadError("Not a table, only one column found. Check the delimiter.")

    headers = _dedup_headers(headers)
    width = len(headers)
    rows = []
    for row in reader:
        if len(row) < width:
            row = row + [""] * (width - len(row))
        rows.append(row)
    if not rows:
        raise LoadError("Header row only, no data rows.")
    return headers, rows


def _column_values(rows, idx, limit=SAMPLE_ROWS):
    values = []
    for row in rows[:limit]:
        if idx < len(row):
            value = row[idx].strip()
            if value:
                values.append(value)
    return values


def _ratio(values, matches):
    if not values:
        return 0.0
    return sum(1 for value in values if matches(value)) / len(values)


def _is_id(value):
    return bool(ID_TOKEN.fullmatch(value)) and not TIMESTAMP.match(value)


def _is_wordy(value):
    return " " in value or len(value) > WORDY_LENGTH or bool(NON_ASCII.search(value))


def profile_columns(headers, rows):
    profiles = []
    sampled_rows = min(len(rows), SAMPLE_ROWS)
    for idx, header in enumerate(headers):
        values = _column_values(rows, idx)
        distinct = len(set(values))
        repeat = 1 - (distinct / len(values)) if values else 0
        profiles.append(
            {
                "idx": idx,
                "header": header,
                "norm": _norm(header),
                "filled": len(values) / sampled_rows if sampled_rows else 0,
                "distinct": distinct,
                "repeat_ratio": repeat,
                "id_ratio": _ratio(values, _is_id),
                "loc_ratio": _ratio(values, LOCATION_CODE.match),
                "name_ratio": _ratio(values, _is_wordy),
                "alpha_ratio": _ratio(values, HAS_LETTER.search),
            }
        )
    return profiles


def _hint_score(norm, hints):
    return 1.0 if any(hint in norm for hint in hints) else 0.0


def _any_header(norms, needles):
    return any(needle in norm for norm in norms for needle in needles)


def _order_score(profile):
    return (
        profile["repeat_ratio"] * ORDER_REPEAT_WEIGHT
        + _hint_score(profile["norm"], ORDER_HINTS) * ORDER_HINT_WEIGHT
    )


def _item_score(profile):
    return (1 - profile["repeat_ratio"]) + _hint_score(profile["norm"], ITEM_HINTS) * ITEM_HINT_WEIGHT


def _pick_location_column(profiles, used_indexes):
    candidates = [p for p in profiles if p["idx"] not in used_indexes]
    hinted = [p for p in candidates if _hint_score(p["norm"], LOC_HINTS)]
    if hinted:
        return max(hinted, key=lambda p: p["filled"])
    shaped = [p for p in candidates if p["loc_ratio"] >= LOC_SHAPE_MIN or p["id_ratio"] >= ID_MIN]
    return max(shaped, key=lambda p: p["id_ratio"]) if shaped else None


def detect_pick_columns(headers, rows):
    profiles = profile_columns(headers, rows)
    id_cols = [p for p in profiles if p["id_ratio"] >= ID_MIN and p["filled"] >= FILLED_MIN]
    if len(id_cols) < MIN_TABLE_COLUMNS:
        raise LoadError("No order code and item code columns found. This does not look like order history.")

    order_col = max(id_cols, key=_order_score)

    item_cands = [
        p
        for p in id_cols
        if p["idx"] != order_col["idx"] and not _hint_score(p["norm"], QUANTITY_HINTS)
    ]
    if not item_cands:
        raise LoadError(
            "No item code column found. There is an order column but the rest are quantities or measures."
        )
    item_col = max(item_cands, key=_item_score)

    loc_col = _pick_location_column(profiles, (order_col["idx"], item_col["idx"]))
    return order_col["idx"], item_col["idx"], (loc_col["idx"] if loc_col else None)


def load_pick_history(raw, location_aisle=None, log=None):
    headers, rows = read_table(raw)
    order_idx, item_idx, loc_idx = detect_pick_columns(headers, rows)
    if log:
        log(
            f"  columns picked: order={headers[order_idx]}, item={headers[item_idx]}"
            + (f", location={headers[loc_idx]}" if loc_idx is not None else "")
        )

    location_aisle = location_aisle or {}
    orders = defaultdict(set)
    frequency = Counter()
    current_aisles = defaultdict(Counter)
    width = len(headers)
    for row_number, row in enumerate(rows, 1):
        if len(row) < width:
            continue
        order = row[order_idx].strip()
        item = row[item_idx].strip()
        if not order or not item or TIMESTAMP.match(item):
            continue
        orders[order].add(item)
        frequency[item] += 1
        if loc_idx is not None:
            aisle = location_aisle.get(row[loc_idx].strip())
            if aisle:
                current_aisles[item][aisle] += 1
        if log and row_number % LOG_EVERY == 0:
            log(f"  read {row_number:,} rows")

    if not orders:
        raise LoadError("File parsed but no valid orders in it.")
    multi_item_orders = sum(
        1 for items in orders.values() if len(items) >= MIN_ITEMS_PER_MULTI_ORDER
    )
    if multi_item_orders == 0:
        raise LoadError(
            "Every order has a single item. Nothing travels together, so there is no affinity to learn."
        )
    return dict(orders), frequency, current_aisles


def detect_location_columns(headers, rows):
    profiles = profile_columns(headers, rows)
    code_col = max(profiles, key=lambda p: p["loc_ratio"] + _hint_score(p["norm"], LOC_HINTS))
    if code_col["loc_ratio"] < LOC_COLUMN_SHAPE_MIN and not _hint_score(code_col["norm"], LOC_HINTS):
        return None, None, None, None
    id_col = next(
        (p for p in profiles if p["norm"] in ("autoid", "id") or "autoid" in p["norm"]), None
    )
    cap_col = next((p for p in profiles if _hint_score(p["norm"], CAP_HINTS)), None)
    del_col = next((p for p in profiles if "deleted" in p["norm"]), None)
    return (
        code_col["idx"],
        id_col["idx"] if id_col else None,
        cap_col["idx"] if cap_col else None,
        del_col["idx"] if del_col else None,
    )


def _cell_capacity(row, cap_idx):
    if cap_idx is None or cap_idx >= len(row):
        return 0
    try:
        return float(row[cap_idx] or 0)
    except ValueError:
        return 0


def load_locations(raw):
    try:
        headers, rows = read_table(raw)
    except LoadError:
        return {}, {}
    code_idx, id_idx, cap_idx, del_idx = detect_location_columns(headers, rows)
    if code_idx is None:
        return {}, {}

    location_aisle = {}
    aisle_capacity = Counter()
    for row in rows:
        if del_idx is not None and del_idx < len(row) and row[del_idx].strip() == DELETED_FLAG:
            continue
        code = row[code_idx].strip() if code_idx < len(row) else ""
        if not LOCATION_CODE.match(code):
            continue
        aisle = code.split("-")[0]
        key = row[id_idx].strip() if (id_idx is not None and id_idx < len(row)) else code
        location_aisle[key] = aisle
        if code.startswith(PICK_AISLE_PREFIX):
            capacity = _cell_capacity(row, cap_idx)
            aisle_capacity[aisle] += capacity if capacity > 0 else 1
    return location_aisle, dict(aisle_capacity)


def _pick_category(profiles):
    exact = [p for p in profiles if p["norm"] in CAT_HINTS]
    if exact:
        return exact[0]

    cats = [p for p in profiles if _hint_score(p["norm"], CAT_HINTS) and "nhom" not in p["norm"]]
    if cats:
        return max(cats, key=lambda p: p["distinct"])
    grouped = [p for p in profiles if _hint_score(p["norm"], CAT_HINTS)]
    return max(grouped, key=lambda p: p["distinct"]) if grouped else None


def _pick_product_id_column(profiles):
    named = next((p for p in profiles if "autoid" in p["norm"] or p["norm"] == "id"), None)
    if named is not None:
        return named
    shaped = [p for p in profiles if p["id_ratio"] >= PRODUCT_ID_SHAPE_MIN]
    return max(shaped, key=lambda p: p["distinct"]) if shaped else None


def _pick_product_name_column(profiles):
    hinted = next((p for p in profiles if _hint_score(p["norm"], NAME_HINTS)), None)
    if hinted is not None:
        return hinted
    wordy = [p for p in profiles if p["name_ratio"] >= NAME_SHAPE_MIN]
    return max(wordy, key=lambda p: p["name_ratio"]) if wordy else None


def detect_product_columns(headers, rows):
    profiles = profile_columns(headers, rows)
    id_col = _pick_product_id_column(profiles)
    name_col = _pick_product_name_column(profiles)
    cat_col = _pick_category(profiles)
    return (
        id_col["idx"] if id_col else None,
        name_col["idx"] if name_col else None,
        cat_col["idx"] if cat_col else None,
    )


def load_products(raw):
    try:
        headers, rows = read_table(raw)
    except LoadError:
        return {}, {}, {}
    id_idx, name_idx, cat_idx = detect_product_columns(headers, rows)
    if id_idx is None:
        return {}, {}, {}
    code_idx = next(
        (
            p["idx"]
            for p in profile_columns(headers, rows)
            if p["norm"] in PRODUCT_CODE_HEADERS
        ),
        None,
    )
    name = {}
    category = {}
    alias = {}
    for row in rows:
        if id_idx >= len(row):
            continue
        key = row[id_idx].strip()
        if not key:
            continue
        name[key] = row[name_idx].strip() if (name_idx is not None and name_idx < len(row)) else key
        if cat_idx is not None and cat_idx < len(row):
            category[key] = row[cat_idx].strip()
        for idx in (code_idx, name_idx):
            if idx is not None and idx < len(row):
                candidate = row[idx].strip()
                if candidate and candidate != key:
                    alias[candidate] = key
    return name, category, alias


def _order_hierarchy(profiles, sampled_rows):
    id_cols = [
        p
        for p in profiles
        if p["id_ratio"] >= ID_MIN
        and p["filled"] >= FILLED_MIN
        and not _hint_score(p["norm"], QUANTITY_HINTS)
    ]
    if len(id_cols) < MIN_TABLE_COLUMNS:
        return False

    distinct_floor = max(ORDER_DISTINCT_FLOOR, sampled_rows * ORDER_DISTINCT_SHARE)
    order_like = [
        p
        for p in id_cols
        if ORDER_REPEAT_MIN <= p["repeat_ratio"] <= ORDER_REPEAT_MAX
        and p["distinct"] >= distinct_floor
        and (p["alpha_ratio"] >= ALPHA_MIN or _hint_score(p["norm"], ORDER_HINTS))
        and not _hint_score(p["norm"], LOC_HINTS)
    ]
    if not order_like:
        return False
    order_idx = max(order_like, key=lambda p: p["distinct"])["idx"]
    item_like = [
        p for p in id_cols if p["idx"] != order_idx and p["repeat_ratio"] < ITEM_REPEAT_MAX
    ]
    return bool(item_like)


def classify_file(raw):
    try:
        headers, rows = read_table(raw)
    except LoadError:
        return "unknown"
    profiles = profile_columns(headers, rows)
    sampled_rows = min(len(rows), SAMPLE_ROWS)
    norms = [p["norm"] for p in profiles]

    has_order_column = _any_header(norms, ORDER_HEADERS)
    has_item_column = _any_header(norms, ITEM_HEADERS)
    has_location_code_column = _any_header(norms, LOCATION_CODE_HEADERS)
    has_product_name_column = _any_header(norms, PRODUCT_NAME_HEADERS)
    has_capacity_column = any(_hint_score(norm, CAP_HINTS) for norm in norms)

    most_location_like = max(profiles, key=lambda p: p["loc_ratio"])
    if has_location_code_column or most_location_like["loc_ratio"] >= LOC_FILE_SHAPE_MIN:
        return "location"
    if has_order_column and has_item_column:
        return "pick"

    if has_product_name_column and not has_order_column:
        return "product"

    if _order_hierarchy(profiles, sampled_rows):
        try:
            detect_pick_columns(headers, rows)
            return "pick"
        except LoadError:
            pass
    if has_capacity_column and most_location_like["loc_ratio"] >= LOC_WITH_CAPACITY_SHAPE_MIN:
        return "location"
    id_idx, name_idx, _ = detect_product_columns(headers, rows)
    if id_idx is not None and name_idx is not None:
        return "product"
    return "unknown"


FILE_SIGNATURES = [
    (role, tuple(_norm(h) for h in headers))
    for role, headers in (SCHEMA.get("file_signatures") or {}).items()
    if not role.startswith("_")
]


def detect_role(raw):
    try:
        headers, _ = read_table(raw)
    except LoadError:
        return None
    present = {_norm(h) for h in headers}
    for role, sig in FILE_SIGNATURES:
        if all(d in present for d in sig):
            return role
    return None