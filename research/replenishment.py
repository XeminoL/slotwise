# %%
import itertools
import random
import re
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import numpy as np

from _common import ACCENT, GOOD, INK, style_fig, rows, kv, F_REFILL, COL_CREATED, COL_ITEM, COL_LOC_FROM, COL_LOC_TO, COL_REFILL_TIME

style_fig(plt)

MAX_AISLE = 40
MAX_PAIRS = 20000
TOP_SKUS = 400
TOP_PAIRS = 500
MIN_DAYS_PER_SKU = 3
JACCARD_STRONG = 0.5
SEED = 42


def az(code):
    m = re.match(r"^([A-Za-z]+)(\d+)", code or "")
    return (m.group(1), int(m.group(2))) if m else (None, None)


# %%
def load():
    ra = np.zeros((MAX_AISLE, MAX_AISLE))
    per_line = 0
    day_sku_dest = Counter()
    sku_days = defaultdict(set)
    n_aisles = 0
    for r in rows(F_REFILL, done_only=True):
        sz, sn = az(r.get(COL_LOC_FROM))
        dz, dn = az(r.get(COL_LOC_TO))
        if sz == "R" and dz == "A" and sn < MAX_AISLE and dn < MAX_AISLE:
            ra[sn][dn] += 1
            n_aisles = max(n_aisles, sn, dn)
        per_line += 1
        date = (r.get(COL_REFILL_TIME) or r.get(COL_CREATED) or "")[:10]
        sku = r.get(COL_ITEM)
        dest = r.get(COL_LOC_TO)
        if date and sku and dest:
            day_sku_dest[(date, sku, dest)] += 1
            sku_days[sku].add(date)
    kv("replenishment moves", f"{per_line:,}")
    return ra, per_line, day_sku_dest, sku_days, n_aisles


ra, per_line, dsd, sku_days, n_aisles = load()


# %%
def heatmap_ra(ra, n_aisles):
    top = n_aisles + 1
    sub = ra[1:top, 1:top]
    shade = np.log1p(sub)
    mid = shade.max() * 0.55
    _, ax = plt.subplots(figsize=(8, 7.2))
    im = ax.imshow(shade, cmap="Blues", origin="lower", aspect="equal")
    ax.set_title("R - A")
    ax.set_xticks(range(n_aisles))
    ax.set_yticks(range(n_aisles))
    ax.set_xticklabels(range(1, top), fontsize=8)
    ax.set_yticklabels(range(1, top), fontsize=8)
    ax.set_xlabel("pick (A)")
    ax.set_ylabel("reserve (R)")
    ax.grid(False)

    for i in range(n_aisles):
        for j in range(n_aisles):
            v = sub[i][j]
            if v > 0:
                color = "white" if shade[i][j] >= mid else "#1A1A1A"
                ax.text(j, i, f"{int(v)}", ha="center", va="center", fontsize=6, color=color)

    plt.colorbar(im, ax=ax, fraction=0.046, label="moves")
    plt.tight_layout()


heatmap_ra(ra, n_aisles)


# %%
def merge_orders(per_line, day_sku_dest):
    merged = len(day_sku_dest)
    saved_trips = per_line - merged
    pct = saved_trips / per_line * 100
    kv("trips saved", f"{saved_trips:,}", f"{pct:.1f}%")

    _, ax = plt.subplots(figsize=(6.2, 4.2))
    bars = ax.bar(["before", "after"], [per_line, merged], color=[ACCENT, GOOD])
    for b, v in zip(bars, [per_line, merged]):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v,
            f"{v:,}",
            ha="center",
            va="bottom",
            color=INK,
            fontweight="bold",
        )
    ax.set_title("Merging orders")
    ax.set_ylabel("replenishment")
    ax.margins(y=0.15)
    plt.tight_layout()


merge_orders(per_line, dsd)


# %%
def lift(sku_days):
    skus = [s for s, d in sku_days.items() if len(d) >= MIN_DAYS_PER_SKU]
    skus = sorted(skus, key=lambda s: -len(sku_days[s]))[:TOP_SKUS]

    def jac(a, b):
        sa, sb = sku_days[a], sku_days[b]
        u = len(sa | sb)
        return len(sa & sb) / u if u else 0

    pairs = list(itertools.combinations(skus, 2))
    rng = random.Random(SEED)
    sample = pairs if len(pairs) <= MAX_PAIRS else rng.sample(pairs, MAX_PAIRS)
    scores = sorted((jac(a, b) for a, b in sample), reverse=True)

    top = [j for j in scores[:TOP_PAIRS] if j > 0]
    mean_top = np.mean(top) if top else 0
    mean_all = np.mean(scores) if scores else 0

    kv("pairs sampled", f"{len(sample):,}", f"random draw from {len(pairs):,} pairs of {len(skus)} SKUs")
    kv("top 500 pairs", f"{mean_top:.3f}")
    kv("average pair", f"{mean_all:.3f}")
    kv(
        "pairs sharing many days",
        f"{sum(1 for j in scores if j >= JACCARD_STRONG):,}",
        f"Jaccard >= {JACCARD_STRONG}",
    )


lift(sku_days)