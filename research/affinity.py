# %%
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import numpy as np

from _common import style_fig, rows, kv, F_PICK, COL_ITEM, COL_ORDER

style_fig(plt)

MIN_ITEMS_PER_BASKET = 2
TOP_PAIRS_SHOWN = 10
MATRIX_ITEMS = 25
HOT_ITEMS = 500
TRUTH_TOPN = 20
GUESS_TOPN = 5
MIN_NEIGHBOURS = 3
AFFINITY_TOPN = 25

VECTOR_SIZE = 48
WINDOW = 8
MIN_COUNT = 3
EPOCHS = 5
RANDOM_SEED = 42
WORKERS = 1


# %%
def load_orders():
    baskets = defaultdict(list)
    for r in rows(F_PICK):
        oid = r.get(COL_ORDER)
        sp = r.get(COL_ITEM)
        if oid and sp:
            baskets[oid].append(sp)
    kv("orders before filter", f"{len(baskets):,}")
    baskets = {k: v for k, v in baskets.items() if len(v) >= 2}
    kv("orders", f"{len(baskets):,}")
    return list(baskets.values())


baskets = load_orders()


# %%
def count_pairs(baskets):
    pair = Counter()
    freq = Counter()
    for b in baskets:
        u = set(b)
        for x in u:
            freq[x] += 1
        for x in u:
            for y in u:
                if x < y:
                    pair[(x, y)] += 1
    kv("pairs seen together", f"{len(pair):,}")
    for (x, y), c in pair.most_common(TOP_PAIRS_SHOWN):
        kv(f"{x} <-> {y}", f"{c} times")
    return pair, freq


pair, freq = count_pairs(baskets)


# %%
def try_word2vec(baskets):
    from gensim.models import Word2Vec

    all_items = set()
    for b in baskets:
        all_items.update(b)
    kv("items before train", f"{len(all_items):,}")

    model = Word2Vec(
        sentences=baskets,
        vector_size=VECTOR_SIZE,
        window=WINDOW,
        min_count=MIN_COUNT,
        epochs=EPOCHS,
        sg=1,
        seed=RANDOM_SEED,
        workers=WORKERS,
    )
    kv("items with vector", f"{len(model.wv):,}")
    return model


model = try_word2vec(baskets)


# %%
def neighbours_by_count(pair):
    co = defaultdict(Counter)
    for (x, y), c in pair.items():
        co[x][y] += c
        co[y][x] += c
    return co


co = neighbours_by_count(pair)


# %%
def compare_with_word2vec(co, freq, model):
    hot = [m for m, _ in freq.most_common(HOT_ITEMS) if m in model.wv]
    hit = checked = 0
    for item in hot:
        truth = set(a for a, _ in co[item].most_common(TRUTH_TOPN))
        if not truth or len(co[item]) < MIN_NEIGHBOURS:
            continue
        checked += 1
        guess = [s for s, _ in model.wv.most_similar(item, topn=GUESS_TOPN)]
        hit += sum(1 for s in guess if s in truth) / GUESS_TOPN
    if not checked:
        kv("error", "not enough items to check")
        return
    kv(
        "accuracy",
        f"{hit / checked * 100:.0f}%",
    )

compare_with_word2vec(co, freq, model)


# %%
def affinity_matrix(co, freq):
    top = [m for m, _ in freq.most_common(AFFINITY_TOPN)]
    n = len(top)
    idx = {m: i for i, m in enumerate(top)}
    matrix = np.zeros((n, n))
    for i, x in enumerate(top):
        for y, c in co[x].items():
            if y in idx:
                matrix[i][idx[y]] = c
    np.fill_diagonal(matrix, 0)

    shade = np.log1p(matrix)
    mid = shade.max() * 0.55
    _, ax = plt.subplots(figsize=(8, 7.2))
    im = ax.imshow(shade, cmap="Blues", aspect="equal")
    ax.set_title("Affinity matrix")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(range(1, n + 1), fontsize=8)
    ax.set_yticklabels(range(1, n + 1), fontsize=8)
    ax.set_xlabel("item")
    ax.set_ylabel("item")
    ax.grid(False)

    for i in range(n):
        for j in range(n):
            v = matrix[i][j]
            if v > 0:
                color = "white" if shade[i][j] >= mid else "#1A1A1A"
                ax.text(j, i, f"{int(v)}", ha="center", va="center", fontsize=6, color=color)

    plt.colorbar(im, ax=ax, fraction=0.046, label="co-occurrence")
    plt.tight_layout()


affinity_matrix(co, freq)