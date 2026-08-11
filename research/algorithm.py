# %%
import re
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import numpy as np

from _common import ACCENT, GOOD, BAD, DIM, INK, style_fig, rows, kv, F_REFILL, COL_ITEM, COL_LOC_FROM, COL_LOC_TO

style_fig(plt)

MIN_MOVES_PER_AISLE = 300
MIN_MOVES_PER_ITEM = 20


def az(code):
    m = re.match(r"^([A-Za-z]+)(\d+)", code or "")
    return (m.group(1), int(m.group(2))) if m else (None, None)


def wmean(pts):
    total = sum(c for _, c in pts)
    if not total:
        return 0.0
    return sum(n * c for n, c in pts) / total


def wmedian(pts):
    ordered = sorted(pts)
    total = sum(c for _, c in ordered)
    if not total:
        return 0
    cum = 0
    for n, c in ordered:
        cum += c
        if cum >= total / 2:
            return n
    return ordered[-1][0]


def tdist(R, pts):
    return sum(abs(R - n) * c for n, c in pts)


# %%
def load_repl():
    src_dest = defaultdict(Counter)
    item_dest = defaultdict(Counter)
    n_aisles = 0
    for r in rows(F_REFILL, done_only=True):
        sz, sn = az(r.get(COL_LOC_FROM))
        dz, dn = az(r.get(COL_LOC_TO))
        if sz == "R" and dz == "A":
            src_dest[sn][dn] += 1
            n_aisles = max(n_aisles, dn)
            sp = r.get(COL_ITEM)
            if sp:
                item_dest[sp][dn] += 1
    kv("reserve aisles", len(src_dest))
    kv("items", f"{len(item_dest):,}")
    kv("pick aisles", n_aisles)
    return src_dest, item_dest, n_aisles


def busiest_aisle(src_dest):
    return max(src_dest, key=lambda k: sum(src_dest[k].values()))


src_dest, item_dest, n_aisles = load_repl()


# %%
def show_spread(src_dest, r=12):
    if r is None:
        r = busiest_aisle(src_dest)
    dc = src_dest[r]
    kv("example", f"R{r}")
    total = sum(dc.values())
    pts = [(n, c) for n, c in dc.items()]
    for n in sorted(dc):
        p = dc[n] / total * 100 if total else 0.0
        if p >= 1:
            print(f"  A{n:<3} {p:4.0f}% {'#' * round(p / 2)}")
    kv("mean", f"A{wmean(pts):.1f}")
    kv("median", f"A{wmedian(pts)}")

show_spread(src_dest)


# %%
def curve(src_dest, n_aisles):
    r = busiest_aisle(src_dest)
    dc = src_dest[r]
    kv("example", f"R{r}")
    pts = [(n, c) for n, c in dc.items()]
    mean = round(wmean(pts))
    med = wmedian(pts)
    mode = max(pts, key=lambda x: x[1])[0]
    xs = list(range(1, n_aisles + 1))
    ys = [tdist(x, pts) for x in xs]
    opt = xs[int(np.argmin(ys))]
    kv("mean", f"A{mean}", f"distance {tdist(mean, pts):,.0f}")
    kv("median", f"A{med}", f"distance {tdist(med, pts):,.0f}")
    kv("mode", f"A{mode}", f"distance {tdist(mode, pts):,.0f}")
    kv("true optimum", f"A{opt}", f"distance {min(ys):,.0f}")

    _, ax = plt.subplots(figsize=(8.4, 4.4))
    ax.plot(xs, ys, color=ACCENT, lw=2)
    ax.fill_between(xs, ys, color=ACCENT, alpha=0.12)
    for x, lb, col in [(mean, "mean", BAD), (med, "median", GOOD), (mode, "mode", DIM)]:
        ax.axvline(x, color=col, ls="--", lw=1.2)
        ax.text(x, max(ys) * 0.96, f" {lb} A{x}", color=col, fontsize=9, rotation=90, va="top")
    ax.scatter([opt], [min(ys)], color=GOOD, zorder=5, s=60, label=f"optimum A{opt}")
    ax.set_title("Total distance for replenishment from a single reserve aisle")
    ax.set_xlabel("reserve placed in aisle")
    ax.set_ylabel("total distance")
    ax.legend()
    plt.tight_layout()


curve(src_dest, n_aisles)


# %%
def compare_all(src_dest, item_dest, n_aisles):
    same = mean_t = median_t = opt_t = 0
    better = worse = 0
    aisle_moves = 0
    for rnum, dc in src_dest.items():
        pts = [(n, c) for n, c in dc.items()]
        aisle_total = sum(c for _, c in pts)
        if aisle_total < MIN_MOVES_PER_AISLE:
            continue
        aisle_moves += aisle_total
        med = wmedian(pts)
        mn = round(wmean(pts))
        opt = min(range(1, n_aisles + 1), key=lambda p: tdist(p, pts))
        d_same = tdist(rnum, pts)
        d_med = tdist(med, pts)
        same += d_same
        mean_t += tdist(mn, pts)
        median_t += d_med
        opt_t += tdist(opt, pts)
        if d_med < d_same:
            better += 1
        elif d_med > d_same:
            worse += 1

    base = same
    kv("same-number", f"{same:>10,.0f}", f"over {aisle_moves:,} moves")
    kv("mean", f"{mean_t:>10,.0f}")
    kv("median", f"{median_t:>10,.0f}")
    kv("absolute optimum", f"{opt_t:>10,.0f}")
    kv("median vs same-number", f"{better} aisles better", f"{worse} aisles worse")

    per = mixed = 0
    item_moves = 0
    all_pts = Counter()
    for dc in item_dest.values():
        for n, c in dc.items():
            all_pts[n] += c
    glob_med = wmedian(list(all_pts.items()))
    for dc in item_dest.values():
        pts = [(n, c) for n, c in dc.items()]
        total = sum(c for _, c in pts)
        if total < MIN_MOVES_PER_ITEM:
            continue
        item_moves += total
        per += tdist(wmedian(pts), pts)
        mixed += tdist(glob_med, pts)
    kv("one median for all", f"{mixed:>10,.0f}", f"over {item_moves:,} moves")
    cheaper_note = f"{(1 - per / mixed) * 100:.0f}% cheaper than the row above" if mixed else ""
    kv("per-item", f"{per:>10,.0f}", cheaper_note)
    kv(
        "note",
        f"{aisle_moves:,} vs {item_moves:,} moves",
        "the aisle branch and the item branch have different denominators, "
        "do not compare them directly",
    )

    _, ax = plt.subplots(figsize=(8.6, 4.4))
    labels = ["same-num", "mean", "median", "absolute\noptimum"]
    vals = [same, mean_t, median_t, opt_t]
    cols = [DIM, BAD, GOOD, GOOD]
    bars = ax.bar(labels, vals, color=cols)
    for b, v in zip(bars, vals):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v,
            f"{(v / base - 1) * 100:+.1f}%" if base else "-",
            ha="center",
            va="bottom",
            color=INK,
            fontsize=10,
            fontweight="bold",
        )
    ax.set_title("Total warehouse replenishment distance by algorithm")
    ax.set_ylabel("total distance")
    ax.margins(y=0.15)
    plt.tight_layout()


compare_all(src_dest, item_dest, n_aisles)