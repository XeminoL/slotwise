# %%
import re
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import numpy as np

from _common import ACCENT, GOOD, BAD, DIM, INK, style_fig, rows, kv, F_PICK, F_REFILL, COL_ITEM, COL_LOC_FROM, COL_LOC_TO, COL_ORDER

style_fig(plt)

FAR_LIMIT = 6
PARTNER_SCALE = (1.0, 0.45, 0.35, 0.25, 0.18, 0.12, 0.0)
MIN_MOVES_PER_ITEM = 20
MIN_PAIR_COUNT = 3
TOP_PARTNERS = 4
SWEEP_STEP = 0.05
W_IN_USE = 0.4
FLAT_MARGIN = 0.01
RANDOM_RUNS = 20
SEED = 42


def az(code):
    m = re.match(r"^([A-Za-z]+)(\d+)", code or "")
    return (m.group(1), int(m.group(2))) if m else (None, None)


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


def closeness(gap):
    return 1 - min(gap, FAR_LIMIT) / FAR_LIMIT


def partner_closeness(gap):
    return PARTNER_SCALE[min(gap, len(PARTNER_SCALE) - 1)]


# %%
def load_refill():
    item_dest = defaultdict(Counter)
    reserve_aisles = set()
    for r in rows(F_REFILL, done_only=True):
        sz, sn = az(r.get(COL_LOC_FROM))
        dz, dn = az(r.get(COL_LOC_TO))
        if sz == "R" and dz == "A":
            reserve_aisles.add(sn)
            sp = r.get(COL_ITEM)
            if sp:
                item_dest[sp][dn] += 1
    item_dest = {k: v for k, v in item_dest.items() if sum(v.values()) >= MIN_MOVES_PER_ITEM}
    kv("items with own refill history", f"{len(item_dest):,}")
    kv("reserve aisles", len(reserve_aisles))
    return item_dest, sorted(reserve_aisles)


def load_partners(item_dest):
    baskets = defaultdict(set)
    for r in rows(F_PICK):
        oid, sp = r.get(COL_ORDER), r.get(COL_ITEM)
        if oid and sp:
            baskets[oid].add(sp)
    tracked = set(item_dest)
    pair = Counter()
    for b in baskets.values():
        u = [x for x in b if x in tracked]
        for i, x in enumerate(u):
            for y in u[i + 1 :]:
                pair[(x, y) if x < y else (y, x)] += 1
    partners = defaultdict(list)
    for (x, y), c in pair.items():
        if c >= MIN_PAIR_COUNT:
            partners[x].append((c, y))
            partners[y].append((c, x))
    partners = {
        k: [m for _, m in sorted(v, reverse=True)[:TOP_PARTNERS]] for k, v in partners.items()
    }
    kv("items with partners", f"{len(partners):,}")
    return partners


def load_orders(item_dest):
    baskets = defaultdict(set)
    for r in rows(F_PICK):
        oid, sp = r.get(COL_ORDER), r.get(COL_ITEM)
        if oid and sp:
            baskets[oid].add(sp)
    tracked = set(item_dest)
    orders = [[x for x in b if x in tracked] for b in baskets.values()]
    orders = [o for o in orders if len(o) >= 2]
    kv(
        "multi-item orders",
        f"{len(orders):,}",
        f"{np.mean([len(o) for o in orders]):.1f} items each",
    )
    return orders


item_dest, reserve_aisles = load_refill()
partners = load_partners(item_dest)
orders = load_orders(item_dest)
capacity = int(np.ceil(len(item_dest) / len(reserve_aisles)))
kv("capacity per aisle", capacity, "even split, nothing may pile into one aisle")


# %%
def assign(w, item_dest, partners, reserve_aisles, capacity):
    order = sorted(item_dest, key=lambda m: (-sum(item_dest[m].values()), m))
    placed = {}
    used = Counter()
    for item in order:
        center = wmedian(list(item_dest[item].items()))
        friends = [placed[p] for p in partners.get(item, []) if p in placed]
        best_score, best_aisle = None, None
        for a in reserve_aisles:
            if used[a] >= capacity:
                continue
            score = (1 - w) * closeness(abs(a - center))
            if friends:
                score += w * partner_closeness(max(abs(a - f) for f in friends))
            if best_score is None or score > best_score:
                best_score, best_aisle = score, a
        placed[item] = best_aisle
        used[best_aisle] += 1
    return placed


def measure(placed, item_dest, orders):
    refill = 0
    for item, a in placed.items():
        refill += sum(abs(a - n) * c for n, c in item_dest[item].items())
    picking = 0
    for line in orders:
        seen = [placed[m] for m in line if m in placed]
        if len(seen) >= 2:
            picking += max(seen) - min(seen)
    return refill, picking


ws = [round(x, 2) for x in np.arange(0, 1 + SWEEP_STEP / 2, SWEEP_STEP)]
sweep = [
    (w,) + measure(assign(w, item_dest, partners, reserve_aisles, capacity), item_dest, orders)
    for w in ws
]
refill_cost = np.array([d for _, d, _ in sweep], dtype=float)
picking_cost = np.array([p for _, _, p in sweep], dtype=float)
total_cost = refill_cost + picking_cost
for w, d, p in sweep:
    if w in (0.0, 0.2, W_IN_USE, 0.6, 0.8, 1.0):
        kv(f"w={w:.2f}", f"refill {d:>9,.0f} + picking {p:>9,.0f} = {d + p:>10,.0f} aisle-moves")


# %%
def when_weight_starts_to_matter(ws, item_dest, partners, reserve_aisles, capacity):
    base = assign(0.0, item_dest, partners, reserve_aisles, capacity)
    moved = []
    for w in ws:
        x = assign(w, item_dest, partners, reserve_aisles, capacity)
        moved.append(sum(1 for m in base if x[m] != base[m]) / len(base) * 100)
    kv("w=0.05 changes", f"{moved[1]:.1f}% of items")
    kv(f"w={W_IN_USE} changes", f"{moved[ws.index(W_IN_USE)]:.1f}% of items")
    kv("w=1.00 changes", f"{moved[-1]:.1f}% of items")

    _, ax = plt.subplots(figsize=(8.4, 4.0))
    ax.plot(ws, moved, color=ACCENT, lw=2, marker="o", ms=3)
    ax.axvline(W_IN_USE, color=GOOD, ls="--", lw=1.4)
    ax.set_xlabel("weight")
    ax.set_ylabel("% items placed differently")
    ax.set_title("Different weight placements")
    plt.tight_layout()
    return moved


moved = when_weight_starts_to_matter(ws, item_dest, partners, reserve_aisles, capacity)


# %%
def two_goals_pull_apart(ws, refill_cost, picking_cost):
    kv("refill", f"{refill_cost.min():,.0f} -> {refill_cost.max():,.0f} aisle-moves")
    kv("picking", f"{picking_cost.min():,.0f} -> {picking_cost.max():,.0f} aisle-moves")
    kv(
        "refill share",
        f"{refill_cost.mean() / (refill_cost + picking_cost).mean() * 100:.0f}%",
        "of the combined cost, on average",
    )

    _, ax = plt.subplots(figsize=(8.6, 4.6))
    ax.plot(ws, refill_cost / 1000, color=BAD, lw=2, marker="o", ms=3, label="refill")
    ax.plot(ws, picking_cost / 1000, color=ACCENT, lw=2, marker="s", ms=3, label="picking")
    ax.plot(ws, (refill_cost + picking_cost) / 1000, color=INK, lw=2.6, label="total")
    ax.axvline(W_IN_USE, color=GOOD, ls="--", lw=1.4)
    ax.text(W_IN_USE, ax.get_ylim()[1], f" in use w={W_IN_USE}", color=GOOD, fontsize=9, va="top")
    ax.set_xlabel("weight")
    ax.set_ylabel("aisle-moves")
    ax.set_title("Refill vs picking costs")
    ax.legend(fontsize=9)
    plt.tight_layout()


two_goals_pull_apart(ws, refill_cost, picking_cost)


# %%
def cheapest_overall(ws, refill_cost, picking_cost, total_cost):
    i = int(np.argmin(total_cost))
    i_use = ws.index(W_IN_USE)
    kv("cheapest w", f"{ws[i]:.2f}", f"{total_cost[i]:,.0f} aisle-moves")
    kv("w in use", f"{W_IN_USE:.2f}", f"{total_cost[i_use]:,.0f} aisle-moves")
    kv(
        "difference",
        f"{total_cost[i_use] - total_cost[i]:,.0f} aisle-moves",
        f"{(total_cost[i_use] / total_cost[i] - 1) * 100:+.1f}%",
    )

    print(f"  {'w':>5} | {'refill':>10} | {'picking':>10} | {'total':>11} | {'vs best':>8}")
    print("  " + "-" * 56)
    for k, w in enumerate(ws):
        if round(w * 100) % 10:
            continue
        tag = "  <-- in use" if abs(w - W_IN_USE) < 1e-9 else ""
        print(
            f"  {w:>5.2f} | {refill_cost[k]:>10,.0f} | {picking_cost[k]:>10,.0f} "
            f"| {total_cost[k]:>11,.0f} | {(total_cost[k] / total_cost[i] - 1) * 100:>+7.1f}%{tag}"
        )

    _, ax = plt.subplots(figsize=(8.6, 4.4))
    ax.plot(ws, total_cost / 1000, color=INK, lw=2.4)
    ax.scatter(
        [ws[i]], [total_cost[i] / 1000], color=GOOD, s=80, zorder=5, label=f"cheapest w={ws[i]:.2f}"
    )
    ax.scatter(
        [W_IN_USE],
        [total_cost[i_use] / 1000],
        color=BAD,
        s=60,
        zorder=5,
        label=f"in use w={W_IN_USE}",
    )
    ax.set_xlabel("weight")
    ax.set_ylabel("total aisle-moves")
    ax.set_title("Total cost across the whole weight range")
    ax.legend(fontsize=9)
    plt.tight_layout()
    return i


i_best = cheapest_overall(ws, refill_cost, picking_cost, total_cost)


# %%
def how_flat_is_the_bottom(ws, total_cost, i_best):
    floor = total_cost[i_best]
    within = [ws[k] for k in range(len(ws)) if total_cost[k] <= floor * (1 + FLAT_MARGIN)]
    kv(
        "within 1% of best",
        f"w = {min(within):.2f} to {max(within):.2f}",
        f"{len(within)} of {len(ws)} values tried",
    )
    kv("w in use inside that range", "yes" if W_IN_USE in within else "no")

    _, ax = plt.subplots(figsize=(8.4, 4.0))
    ax.plot(ws, (total_cost / floor - 1) * 100, color=INK, lw=2)
    ax.axhspan(0, FLAT_MARGIN * 100, color=GOOD, alpha=0.15)
    ax.axvline(W_IN_USE, color=BAD, ls="--", lw=1.4)
    ax.text(W_IN_USE, ax.get_ylim()[1], f" in use w={W_IN_USE}", color=BAD, fontsize=9, va="top")
    ax.set_xlabel("weight")
    ax.set_ylabel("% above cheapest")
    ax.set_title("Total cost relative to cheapest weight")
    plt.tight_layout()


how_flat_is_the_bottom(ws, total_cost, i_best)


# %%
def against_random(item_dest, partners, orders, reserve_aisles, capacity, total_cost, i_best):
    rng = np.random.default_rng(SEED)
    totals = []
    for _ in range(RANDOM_RUNS):
        slots = list(reserve_aisles) * capacity
        rng.shuffle(slots)
        blind = {m: int(slots[k]) for k, m in enumerate(item_dest)}
        d, p = measure(blind, item_dest, orders)
        totals.append(d + p)
    rand = float(np.mean(totals))
    i_use = ws.index(W_IN_USE)
    kv("random placement", f"{rand:,.0f} aisle-moves")
    kv(
        f"w={W_IN_USE}",
        f"{total_cost[i_use]:,.0f}",
        f"-{(1 - total_cost[i_use] / rand) * 100:.1f}%",
    )
    kv(
        f"w={ws[i_best]:.2f} (best)",
        f"{total_cost[i_best]:,.0f}",
        f"-{(1 - total_cost[i_best] / rand) * 100:.1f}%",
    )

    _, ax = plt.subplots(figsize=(7.6, 4.2))
    labels = ["random", f"w={W_IN_USE}\n(in use)", f"w={ws[i_best]:.2f}\n(cheapest)"]
    vals = [rand, total_cost[i_use], total_cost[i_best]]
    bars = ax.bar(labels, vals, color=[DIM, ACCENT, GOOD])
    for b, v in zip(bars, vals):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v,
            f"{v:,.0f}",
            ha="center",
            va="bottom",
            color=INK,
            fontweight="bold",
            fontsize=9,
        )
    ax.set_title("Total cost with random placement")
    ax.set_ylabel("aisle-moves")
    ax.margins(y=0.15)
    plt.tight_layout()


against_random(item_dest, partners, orders, reserve_aisles, capacity, total_cost, i_best)


# %%
def if_refill_is_worth_more(ws, refill_cost, picking_cost):
    ratios = [0.5, 1.0, 1.5, 2.0, 3.0]
    print(f"  {'refill trip costs':>18} | {'best w':>7} | {'w=0.4 penalty':>14}")
    print("  " + "-" * 45)
    picks = []
    for r in ratios:
        blended = r * refill_cost + picking_cost
        i = int(np.argmin(blended))
        penalty = (blended[ws.index(W_IN_USE)] / blended[i] - 1) * 100
        picks.append(ws[i])
        print(f"  {r:>16.1f}x | {ws[i]:>7.2f} | {penalty:>13.1f}%")
    kv(
        "best w ranges",
        f"{min(picks):.2f} to {max(picks):.2f}",
        "even when one trip is worth 3x the other",
    )


if_refill_is_worth_more(ws, refill_cost, picking_cost)