import statistics
from collections import Counter, defaultdict

from gensim.models import Word2Vec
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from umap import UMAP

from config import SCHEMA

PICK_AISLE_PREFIX = "A"
CLUSTER_COUNT = 60
FILL_RATIO = 0.8
MAP_DRAW_COUNT = 999999
COMPANION_COUNT = 6


BIG_DATASET = 500
SMALL_DIMS, BIG_DIMS = 16, 64
SMALL_EPOCHS, BIG_EPOCHS = 40, 5
SMALL_MIN_COUNT, BIG_MIN_COUNT = 1, 5
AVG_DECIMALS = 3

MIN_ITEMS_PER_SENTENCE = 2
WINDOW = 10
NEGATIVE_SAMPLES = 10
RANDOM_SEED = 42
WORKERS = 1
KMEANS_RESTARTS = 10

MAP_DIMENSIONS = 2
PCA_DIMENSIONS = 50
UMAP_NEIGHBORS_MAX = 30
UMAP_NEIGHBORS_MIN = 2
UMAP_MIN_DIST = 0.1
UMAP_METRIC = "cosine"
COORD_DECIMALS = 4

FAST_RANK_MIN = 0.8
MEDIUM_RANK_MIN = 0.4
UNKNOWN_CATEGORY = "Unknown category"

FLOOR_LOW = "low floor preferred"
FLOOR_MIDDLE = "middle floor"
FLOOR_HIGH = "high floor / reserve"

CATEGORY_NAMES = {
    k: v for k, v in (SCHEMA.get("category_names") or {}).items()
    if not k.startswith("_")
}


def learn_embeddings(orders):
    sentences = [
        sorted(items)
        for _, items in sorted(orders.items())
        if len(items) >= MIN_ITEMS_PER_SENTENCE
    ]
    if not sentences:
        return None
    big = len(sentences) >= BIG_DATASET

    return Word2Vec(
        sentences,
        vector_size=BIG_DIMS if big else SMALL_DIMS,
        window=WINDOW,
        min_count=BIG_MIN_COUNT if big else SMALL_MIN_COUNT,
        sg=1,
        negative=NEGATIVE_SAMPLES,
        epochs=BIG_EPOCHS if big else SMALL_EPOCHS,
        seed=RANDOM_SEED,
        workers=WORKERS,
    )


def cluster_items(model):
    items = list(model.wv.index_to_key)
    n_clusters = min(CLUSTER_COUNT, len(items))
    labels = KMeans(
        n_clusters=n_clusters, random_state=RANDOM_SEED, n_init=KMEANS_RESTARTS
    ).fit_predict(model.wv[items])
    clusters = defaultdict(list)
    for item, label in zip(items, labels):
        clusters[label].append(item)
    return clusters


def dominant_category(items, category):
    found = [category.get(item) for item in items if category.get(item)]
    if not found:
        return "?"
    return min(Counter(found).items(), key=lambda kv: (-kv[1], kv[0]))[0]


def assign_clusters_to_aisles(clusters, aisle_capacity, frequency, category):
    grouped = defaultdict(list)
    for items in clusters.values():
        grouped[dominant_category(items, category)].extend(items)

    ranked_categories = [
        grouped[name]
        for name in sorted(
            grouped,
            key=lambda name: (-sum(frequency.get(item, 0) for item in grouped[name]), name),
        )
    ]
    ranked_aisles = sorted(aisle_capacity.items(), key=lambda kv: (-kv[1], kv[0]))
    room = [(aisle, int(capacity * FILL_RATIO)) for aisle, capacity in ranked_aisles]

    item_to_aisle = {}
    aisle_cursor = 0
    for items in ranked_categories:
        for item in sorted(items, key=lambda i: (-frequency.get(i, 0), i)):
            while aisle_cursor < len(room) and room[aisle_cursor][1] <= 0:
                aisle_cursor += 1
            if aisle_cursor >= len(room):
                break
            aisle, free = room[aisle_cursor]
            item_to_aisle[item] = aisle
            room[aisle_cursor] = (aisle, free - 1)
    return item_to_aisle


def _avg_aisles(orders, item_to_aisle):
    total = n_orders = 0
    for items in orders.values():
        aisles_hit = {item_to_aisle[item] for item in items if item in item_to_aisle}
        if aisles_hit:
            total += len(aisles_hit)
            n_orders += 1
    return total / n_orders if n_orders else 0


def speed_rank(pick_count, sorted_counts):
    if not sorted_counts:
        return 0.0
    slower = sum(1 for count in sorted_counts if count < pick_count)
    return slower / len(sorted_counts)


def floor_hint_for_rank(rank):
    if rank >= FAST_RANK_MIN:
        return FLOOR_LOW
    if rank >= MEDIUM_RANK_MIN:
        return FLOOR_MIDDLE
    return FLOOR_HIGH


def count_companions(orders, target_items):
    targets = set(target_items)
    pair_counts = defaultdict(Counter)
    for _, items in sorted(orders.items()):
        present = sorted(item for item in items if item in targets)
        for item in present:
            for companion in present:
                if item != companion:
                    pair_counts[item][companion] += 1
    return {
        item: sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:COMPANION_COUNT]
        for item, counter in pair_counts.items()
    }


def _cluster_of_item(clusters):
    item_cluster = {}
    for label, items in clusters.items():
        for item in items:
            item_cluster[item] = label
    return item_cluster


def _ranked_items(frequency, advice, limit=None):
    ranked = sorted(
        (item for item in frequency if item in advice),
        key=lambda item: (-frequency[item], item),
    )
    return ranked if limit is None else ranked[:limit]


def build_advice(clusters, item_to_aisle, name, category, frequency, current_aisles):
    item_cluster = _cluster_of_item(clusters)
    sorted_counts = sorted(frequency.values())

    advice = {}
    for item, aisle in item_to_aisle.items():
        rank = speed_rank(frequency.get(item, 0), sorted_counts)
        spread = current_aisles.get(item, Counter())
        advice[item] = {
            "name": name.get(item, item),
            "category": CATEGORY_NAMES.get(category.get(item), UNKNOWN_CATEGORY),
            "aisle": aisle,
            "floor": floor_hint_for_rank(rank),
            "cluster_size": len(clusters[item_cluster[item]]),
            "pick_count": frequency.get(item, 0),
            "speed_rank": round(rank * 100),
            "spread_count": len(
                [aisle for aisle in spread if aisle.startswith(PICK_AISLE_PREFIX)]
            ),
            "current_aisle": _top_aisle(spread) if spread else None,
        }
    return advice


def _reduce_noise(vectors):
    """PCA before UMAP: drop noisy dimensions so UMAP runs faster and clusters cleaner.

    This is what sklearn recommends for t-SNE and it carries over to UMAP.
    """
    target = min(PCA_DIMENSIONS, vectors.shape[0], vectors.shape[1])
    if target >= vectors.shape[1]:
        return vectors
    reduced = PCA(n_components=target, random_state=RANDOM_SEED).fit_transform(vectors)
    return reduced


def map_coordinates(model, items):
    vectors = _reduce_noise(model.wv[items])
    neighbors = min(UMAP_NEIGHBORS_MAX, max(UMAP_NEIGHBORS_MIN, len(items) - 1))
    coords = UMAP(
        n_components=MAP_DIMENSIONS,
        random_state=RANDOM_SEED,
        n_neighbors=neighbors,
        min_dist=UMAP_MIN_DIST,
        metric=UMAP_METRIC,
    ).fit_transform(vectors)
    xs, ys = coords[:, 0], coords[:, 1]
    x_min, x_range = xs.min(), (xs.max() - xs.min()) or 1
    y_min, y_range = ys.min(), (ys.max() - ys.min()) or 1
    return {
        item: [
            round(float((x - x_min) / x_range), COORD_DECIMALS),
            round(float((y - y_min) / y_range), COORD_DECIMALS),
        ]
        for item, x, y in zip(items, xs, ys)
    }


def build_map(model, advice, clusters, frequency):
    item_cluster = _cluster_of_item(clusters)

    top_items = _ranked_items(frequency, advice, MAP_DRAW_COUNT)
    if not top_items:
        return []
    coords = map_coordinates(model, top_items)
    return [
        {
            "id": item,
            "name": advice[item]["name"],
            "x": coords[item][0],
            "y": coords[item][1],
            "cluster": int(item_cluster[item]),
            "category": advice[item]["category"],
            "aisle": advice[item]["aisle"],
        }
        for item in top_items
    ]


def _top_aisle(counter):
    """Most picked aisle. On a tie take the smaller code so results stay deterministic."""
    return min(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def backtest(orders, item_to_aisle, current_aisles):
    current_main = {
        item: _top_aisle(counter) for item, counter in current_aisles.items() if counter
    }
    before_sum = after_sum = n_orders = 0
    for items in orders.values():
        before = {current_main[item] for item in items if item in current_main}
        after = {item_to_aisle[item] for item in items if item in item_to_aisle}
        if not before or not after:
            continue
        before_sum += len(before)
        after_sum += len(after)
        n_orders += 1
    if not n_orders:
        return None
    before_avg = before_sum / n_orders
    after_avg = after_sum / n_orders
    drop = (before_avg - after_avg) / before_avg * 100 if before_avg else 0
    return {
        "orders": n_orders,
        "before": round(before_avg, 2),
        "after": round(after_avg, 2),
        "reduction": round(drop, 1),
    }


def cluster_purity(clusters, category):
    correct = total = 0
    for items in clusters.values():
        main_cat = dominant_category(items, category)
        for item in items:
            if category.get(item):
                total += 1
                if category.get(item) == main_cat:
                    correct += 1
    return round(correct / total * 100) if total else 0


_last_model = None
_last_clusters = None


def run(orders, frequency, current_aisles, aisle_capacity, name, category, log=print):
    global _last_model, _last_clusters
    log("Learning affinity (embedding)...")
    model = learn_embeddings(orders)
    if model is None:
        raise ValueError("Not enough multi-item orders to learn from. Orders need at least 2 items.")

    log("Clustering...")
    clusters = cluster_items(model)
    _last_model = model
    _last_clusters = clusters

    log("Assigning aisles...")
    item_to_aisle = assign_clusters_to_aisles(clusters, aisle_capacity, frequency, category)
    opt_stats = {"seed_avg_full": round(_avg_aisles(orders, item_to_aisle), AVG_DECIMALS)}

    log("Building suggestions...")
    advice = build_advice(clusters, item_to_aisle, name, category, frequency, current_aisles)

    log("Counting items that ship together (all items)...")
    map_items = _ranked_items(frequency, advice)
    companions = count_companions(orders, map_items)
    for item, pairs in companions.items():
        advice[item]["companions"] = [
            {"name": advice[companion]["name"], "count": count}
            for companion, count in pairs
            if companion in advice
        ]

    log("Drawing affinity map...")
    gu_map = build_map(model, advice, clusters, frequency)

    log("Measuring before/after (backtest)...")
    backtest_stats = backtest(orders, item_to_aisle, current_aisles)
    purity = cluster_purity(clusters, category)

    spreads = [
        entry["spread_count"] for entry in advice.values() if entry["spread_count"] > 0
    ]
    return {
        "advice": advice,
        "gu_map": gu_map,
        "stats": {
            "orders": len(orders),
            "items": len(advice),
            "aisles": len(set(item_to_aisle.values())),
            "purity": purity,
            "backtest": backtest_stats,
            "spread_median": statistics.median(spreads) if spreads else 0,
            "optimize": opt_stats,
        },
    }