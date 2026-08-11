import math
import pickle
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from core import engine, cell as oc, rmap, refill, weight
from config import CACHE, MIN_PICKS_TRUST

BRAIN_FILE = CACHE / "brain.pkl"


SURE = "chac"
INFERRED = "suy_doan"
GUESS = "doan_mo"

MAX_CANDIDATES = 5
TOP_COMPANIONS = 5

NEIGHBOR_WEIGHT = 0.18
MIN_CANDIDATES = 3

W_NEAR_REFILL = 0.6
W_NEAR_COMPANIONS = 0.4
W_NEAR_COMPANIONS_DECLARED = 0.7
MAX_REFILL_DISTANCE = 6

NEIGHBOR_DISTANCES = (1, 2, 3)
COMPANION_PROXIMITY_BY_GAP = (1.0, 0.45, 0.35, 0.25, 0.18, 0.12, 0.0)
TIE_BREAK_SHARE = 1000
TOP_RESERVE_DAYS = 4
TOP_COMP_NAMES = 4
FALLBACK_AISLE_DISTANCE = 999
TUNE_ROUNDS = 3
ANNEAL_SEED = 42
ANNEAL_START_TEMP = 0.08
ANNEAL_MIN_TEMP = 1e-9
ANNEAL_STEPS_PER_ITEM = 12
ANNEAL_MIN_STEPS = 60
ANNEAL_MAX_STEPS = 2000
SCORE_DECIMALS = 1
SCORE_PART_NAMES = ("refill", "companion")


def build(orders, frequency, current_aisles, aisle_capacity, name, category, alias=None, log=print):
    payload = engine.run(orders, frequency, current_aisles, aisle_capacity, name, category, log=log)
    model = engine._last_model
    advice = payload["advice"]

    log("Storing cluster centroids...")
    clusters = engine._last_clusters
    centroids = {}
    cluster_aisle = {}
    for label, items in clusters.items():
        vecs = [model.wv[i] for i in items if i in model.wv]
        if vecs:
            centroids[label] = np.mean(vecs, axis=0)
        aisles = Counter(advice[i]["aisle"] for i in items if i in advice)
        if aisles:
            cluster_aisle[label] = aisles.most_common(1)[0][0]

    aisles_by_category = defaultdict(Counter)
    for adv in advice.values():
        aisles_by_category[adv["category"]][adv["aisle"]] += 1
    category_aisle = {
        category_name: aisles.most_common(1)[0][0]
        for category_name, aisles in aisles_by_category.items()
    }

    return {
        "model": model,
        "advice": advice,
        "centroids": centroids,
        "cluster_aisle": cluster_aisle,
        "category_aisle": category_aisle,
        "aisles": sorted(set(a["aisle"] for a in advice.values())),
        "gu_map": payload["gu_map"],
        "stats": payload["stats"],
        "meta": {"orders": len(orders), "items": len(advice)},
        "alias": alias or {},
    }


def save(brain, path=BRAIN_FILE):
    with open(path, "wb") as f:
        pickle.dump(brain, f, protocol=pickle.HIGHEST_PROTOCOL)


def load(path=BRAIN_FILE):
    if not Path(path).exists():
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def exists(path=BRAIN_FILE):
    return Path(path).exists()


def _snap_vector_to_aisle(brain, vector):
    best_label, best_dist = None, float("inf")
    for label, centroid in brain["centroids"].items():
        dist = float(np.linalg.norm(vector - centroid))
        if dist < best_dist:
            best_dist, best_label = dist, label
    if best_label is None:
        return None
    return brain["cluster_aisle"].get(best_label)


def _aisle_of(brain, code):
    resolved = _resolve(brain, code)
    return brain["advice"].get(resolved, {}).get("aisle")


def _neighbor_aisles(brain, aisle):
    matched = re.match(r"^([A-Za-z]+)(\d+)$", aisle or "")
    if not matched:
        return []
    prefix, num = matched.group(1), int(matched.group(2))
    known_aisles = set(brain.get("aisles", []))
    neighbors = []
    for distance in NEIGHBOR_DISTANCES:
        for neighbor_num in (num - distance, num + distance):
            neighbor = f"{prefix}{neighbor_num:02d}"
            if neighbor in known_aisles and neighbor != aisle:
                neighbors.append(neighbor)
    return neighbors


def _score_candidates(brain, companions, chosen_aisle):
    score = defaultdict(float)
    used = []
    for comp in companions or []:
        code = comp.get("name") or comp.get("id")
        if not code:
            continue
        order_count = comp.get("count") or 1
        aisle = _aisle_of(brain, code)
        if aisle:
            score[aisle] += order_count
            used.append({"name": code, "count": order_count})

    if not score:
        return [], {"companion_count": 0, "top_companions": []}

    if chosen_aisle and chosen_aisle not in score:
        score[chosen_aisle] = 0.0

    _fill_neighbor_candidates(brain, score, chosen_aisle)

    total = sum(score.values())
    ranked = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_CANDIDATES]
    candidates = [
        {
            "aisle": aisle,
            "score": round(value, SCORE_DECIMALS),
            "share_pct": round(value / total * 100) if total else 0,
        }
        for aisle, value in ranked
    ]

    used.sort(key=lambda c: -c["count"])
    evidence = {
        "companion_count": len(used),
        "top_companions": used[:TOP_COMPANIONS],
    }
    return candidates, evidence


def _fill_neighbor_candidates(brain, score, chosen_aisle):
    base = chosen_aisle or (max(score, key=score.get) if score else None)
    if not base:
        return
    top_score = max(score.values()) or 1
    for rank, neighbor in enumerate(_neighbor_aisles(brain, base)):
        if len(score) >= MIN_CANDIDATES:
            break
        if neighbor not in score:
            score[neighbor] = top_score * (NEIGHBOR_WEIGHT / (rank + 1))


def _companion_aisles(brain, companions):
    id_by_name, pick_by_name = {}, {}
    for item_id, adv in brain["advice"].items():
        name = adv.get("name")
        if name and name not in id_by_name:
            id_by_name[name] = item_id
            if adv.get("aisle"):
                pick_by_name[name] = adv["aisle"]
    located = []
    for comp in companions or []:
        name = comp.get("name") if isinstance(comp, dict) else comp
        if not name:
            continue
        own_refill = refill.for_item(id_by_name.get(name))
        if own_refill and own_refill.get("days"):
            reserve_days = _reserve_days_from_own(own_refill)
            pick_aisle = own_refill["days"][0].get("aisle")
        else:
            pick_aisle = pick_by_name.get(name)
            reserve_days = rmap.storage_for(pick_aisle) if pick_aisle else None
        if not reserve_days:
            continue
        located.append(
            {
                "name": name,
                "pick_aisle": pick_aisle,
                "aisle": reserve_days[0]["aisle"],
            }
        )
    return located


def _attach_evidence(brain, result, companions):
    candidates, evidence = _score_candidates(brain, companions, result.get("aisle"))
    result["candidates"] = candidates
    result["evidence"] = evidence
    result["companion_aisles"] = _companion_aisles(brain, companions)
    return result


def place_known(brain, item_id):
    adv = brain["advice"][item_id]
    conf = SURE if adv["pick_count"] >= MIN_PICKS_TRUST else INFERRED
    reason = "found in pick history"
    if adv["pick_count"] < MIN_PICKS_TRUST:
        reason = f"thin history (picked {adv['pick_count']} times)"
    companions = adv.get("companions", [])
    result = {
        "item": item_id,
        "name": adv["name"],
        "category": adv["category"],
        "aisle": adv["aisle"],
        "floor": adv["floor"],
        "confidence": conf,
        "reason": reason,
        "companions": companions,
    }
    return _attach_evidence(brain, result, companions)


def place_with_orders(brain, item_id, companion_ids, name=None, category=None):
    model = brain.get("model")
    if model is None:
        return None
    known = [c for c in companion_ids if c in model.wv]
    if not known:
        return None
    vector = np.mean([model.wv[c] for c in known], axis=0)
    aisle = _snap_vector_to_aisle(brain, vector)
    if aisle is None:
        return None
    companions = [{"name": brain["advice"].get(c, {}).get("name", c), "count": 1} for c in known]
    result = {
        "item": item_id,
        "name": name or item_id,
        "category": engine.CATEGORY_NAMES.get(category, "Unknown category"),
        "aisle": aisle,
        "floor": "middle floor",
        "confidence": INFERRED,
        "reason": f"inferred from {len(known)} known items it ships with",
        "companions": companions,
    }
    return _attach_evidence(brain, result, companions)


def place_by_category(brain, item_id, category, name=None):
    cat_name = engine.CATEGORY_NAMES.get(category, category)
    aisle = brain["category_aisle"].get(cat_name)
    if aisle is None:
        return None
    result = {
        "item": item_id,
        "name": name or item_id,
        "category": cat_name,
        "aisle": aisle,
        "floor": "middle floor",
        "confidence": INFERRED,
        "reason": f"placed by category ({cat_name})",
        "companions": [],
    }
    return _attach_evidence(brain, result, [])


def place_unknown(brain, item_id, name=None):
    return {
        "item": item_id,
        "name": name or item_id,
        "category": "",
        "aisle": None,
        "cell": None,
        "floor": None,
        "confidence": GUESS,
        "reason": "Item not in the data. Check the code, or have staff pick a location.",
        "companions": [],
        "candidates": [],
        "not_found": True,
    }


def _resolve(brain, code):
    code = (code or "").strip()
    matched = re.match(r"(?i)^sku[-\s]?(\d+)$", code)
    if matched:
        code = matched.group(1)
    if code in brain["advice"]:
        return code
    return brain.get("alias", {}).get(code, code)


def place(
    brain, item_id, companion_ids=None, category=None, name=None, used_cells=None, group_aisles=None
):
    typed = item_id
    resolved = _resolve(brain, item_id)
    declared = [_resolve(brain, c) for c in (companion_ids or [])]
    declared = [c for c in declared if c != resolved and c in brain["advice"]]
    if resolved in brain["advice"]:
        result = place_known(brain, resolved)

        if declared:
            known_names = {c.get("name") for c in result.get("companions", [])}
            for code in declared:
                name_of_code = brain["advice"][code].get("name", code)
                if name_of_code not in known_names:
                    result.setdefault("companions", []).append({"name": name_of_code, "count": 1})
            result["reason"] += " + filtered by declared items"
            result["by_filter"] = True
        if category and not result.get("category"):
            result["category"] = engine.CATEGORY_NAMES.get(category, category)
    else:
        result = None
        if declared:
            result = place_with_orders(brain, resolved, declared, name, category)
            if result is not None:
                result["by_filter"] = True
        if result is None and category:
            result = place_by_category(brain, resolved, category, name)
        if result is None:
            result = place_unknown(brain, resolved, name)
    result["typed"] = typed
    result["_internal"] = resolved
    speed_rank = brain["advice"].get(resolved, {}).get("speed_rank")

    pull_aisles = set(group_aisles) if group_aisles else set()
    for code in declared:
        declared_aisle = brain["advice"].get(code, {}).get("aisle")
        if declared_aisle:
            pull_aisles.add(declared_aisle)
    _enrich_full_location(
        result,
        used_cells,
        speed_rank,
        brain,
        pull_aisles if declared else group_aisles,
        strong_neighbor=bool(declared),
    )
    if declared and group_aisles is not None:
        group_aisles.add(result.get("aisle"))
    return result


def _speed_rank_of(brain, internal):
    if not (brain and internal):
        return None
    return brain["advice"].get(internal, {}).get("speed_rank")


def _batch_score(tunable, aisle_counts):
    total = 0.0
    for result in tunable:
        neighbors = _neighbors_excluding(aisle_counts, result["aisle"])
        chosen = next(
            (d for d in result["_reserve_days"] if d["aisle"] == result["aisle"]), None
        )
        if chosen is not None:
            total += _rail_score(chosen, neighbors)
    return total


def _neighbors_excluding(aisle_counts, own_aisle):
    if aisle_counts.get(own_aisle, 0) > 1:
        return set(aisle_counts)
    return {a for a in aisle_counts if a != own_aisle}


def _apply_reserve(result, reserve):
    result["aisle"] = reserve["aisle"]
    result["spread"] = reserve.get("spread")
    if "center" in reserve:
        result["serve_center"] = reserve["center"]


def _anneal_batch(tunable, rounds):
    """Simulated annealing over the batch being looked up.

    Unlike greedy local search, this accepts a worse move now and then based on
    temperature, so it escapes local optima when items in the batch pull in
    different directions.
    """
    rng = random.Random(ANNEAL_SEED)
    steps = min(
        max(len(tunable) * rounds * ANNEAL_STEPS_PER_ITEM, ANNEAL_MIN_STEPS),
        ANNEAL_MAX_STEPS,
    )

    aisle_counts = Counter(r["aisle"] for r in tunable)
    current = _batch_score(tunable, aisle_counts)
    best_score = current
    best = {id(r): _reserve_state(r) for r in tunable}

    for step in range(steps):
        temp = ANNEAL_START_TEMP * (1 - step / steps)
        result = tunable[rng.randrange(len(tunable))]
        reserves = result["_reserve_days"]
        if len(reserves) < 2:
            continue
        reserve = reserves[rng.randrange(len(reserves))]
        old_aisle = result["aisle"]
        if reserve["aisle"] == old_aisle:
            continue

        before = _reserve_state(result)
        _apply_reserve(result, reserve)
        aisle_counts[old_aisle] -= 1
        if not aisle_counts[old_aisle]:
            del aisle_counts[old_aisle]
        aisle_counts[reserve["aisle"]] += 1

        candidate = _batch_score(tunable, aisle_counts)
        delta = candidate - current
        if delta > 0 or (temp > ANNEAL_MIN_TEMP and rng.random() < math.exp(delta / temp)):
            current = candidate
            if candidate > best_score:
                best_score = candidate
                best = {id(r): _reserve_state(r) for r in tunable}
        else:
            aisle_counts[reserve["aisle"]] -= 1
            if not aisle_counts[reserve["aisle"]]:
                del aisle_counts[reserve["aisle"]]
            aisle_counts[old_aisle] += 1
            for key, value in before.items():
                result[key] = value

    for result in tunable:
        for key, value in best[id(result)].items():
            result[key] = value

    final_counts = Counter(r["aisle"] for r in tunable)
    return {id(r): _neighbors_excluding(final_counts, r["aisle"]) for r in tunable}


def _reserve_state(result):
    return {
        "aisle": result["aisle"],
        "spread": result.get("spread"),
        "serve_center": result.get("serve_center"),
    }


def tune_batch(result_list, brain=None, used_cells=None, rounds=TUNE_ROUNDS):
    tunable = [r for r in result_list if r.get("_reserve_days") and r.get("aisle")]
    if len(tunable) < 2:
        return result_list

    final_neighbors = _anneal_batch(tunable, rounds)

    oc.release({result.get("_internal") for result in tunable})
    used = used_cells if used_cells is not None else set()
    used.clear()
    for result in tunable:
        internal = result.get("_internal")
        result["aisle"] = _assign_cell(
            result,
            result["aisle"],
            used,
            _speed_rank_of(brain, internal),
            weight.heavy(internal) if internal else None,
        )

    for result in tunable:
        internal = result.get("_internal")
        _build_candidates(
            result,
            result["_reserve_days"],
            result["aisle"],
            result.get("companions", []),
            used,
            _speed_rank_of(brain, internal),
            weight.heavy(internal) if internal else None,
            final_neighbors.get(id(result), set()),
        )
    for result in result_list:
        result.pop("_reserve_days", None)
    return result_list


def _reserve_days_from_own(own_refill):
    center = own_refill["center"]
    reserve_days = [
        {
            "aisle": f"R{center:02d}",
            "share_pct": own_refill["days"][0]["pct"],
            "center": center,
            "spread": own_refill["spread"],
            "dist": 0,
        }
    ]
    for entry in own_refill["days"][1:TOP_RESERVE_DAYS]:
        aisle_num = int(entry["aisle"][1:])
        reserve_days.append(
            {
                "aisle": f"R{aisle_num:02d}",
                "share_pct": entry["pct"],
                "center": center,
                "spread": own_refill["spread"],
                "dist": abs(aisle_num - center),
            }
        )
    return reserve_days


def _aisle_num(aisle):
    m = re.search(r"\d+", aisle or "")
    return int(m.group()) if m else None


def _mean_gap_to_companions(reserve_num, companion_aisles):
    total_weight = 0.0
    weighted_gap = 0.0
    for aisle, order_count in companion_aisles:
        companion_num = _aisle_num(aisle)
        if companion_num is None:
            continue
        order_count = max(float(order_count or 0), 0.0) or 1.0
        weighted_gap += abs(reserve_num - companion_num) * order_count
        total_weight += order_count
    return (weighted_gap / total_weight) if total_weight else None


def _companion_proximity(reserve, group_aisles):
    reserve_num = _aisle_num(reserve["aisle"])
    if reserve_num is None:
        return None
    companion_aisles = reserve.get("_companion_aisles")
    if companion_aisles:
        gap = _mean_gap_to_companions(reserve_num, companion_aisles)
    else:
        nums = [_aisle_num(a) for a in (group_aisles or []) if _aisle_num(a) is not None]
        gap = max(abs(reserve_num - n) for n in nums) if nums else None
    if gap is None:
        return None
    return _interpolate_companion_proximity(gap)


def _interpolate_companion_proximity(gap):
    if gap <= 0:
        return COMPANION_PROXIMITY_BY_GAP[0]
    last = len(COMPANION_PROXIMITY_BY_GAP) - 1
    if gap >= last:
        return COMPANION_PROXIMITY_BY_GAP[last]
    lower = int(gap)
    fraction = gap - lower
    return (
        COMPANION_PROXIMITY_BY_GAP[lower] * (1 - fraction)
        + COMPANION_PROXIMITY_BY_GAP[lower + 1] * fraction
    )


def _score_terms(reserve, group_aisles, strong_neighbor=False):
    w_companions = W_NEAR_COMPANIONS_DECLARED if strong_neighbor else W_NEAR_COMPANIONS
    w_refill = W_NEAR_REFILL if w_companions == W_NEAR_COMPANIONS else 1 - w_companions
    near_refill = 1 - min(reserve.get("dist", 0), MAX_REFILL_DISTANCE) / MAX_REFILL_DISTANCE
    return [
        (near_refill, w_refill),
        (_companion_proximity(reserve, group_aisles), w_companions),
    ]


def _raw_score(reserve, group_aisles, strong_neighbor=False):
    terms = [
        (value, term_weight)
        for value, term_weight in _score_terms(reserve, group_aisles, strong_neighbor)
        if value is not None
    ]
    total_weight = sum(term_weight for _, term_weight in terms)
    if not total_weight:
        return 0.0
    return sum(value * term_weight for value, term_weight in terms) / total_weight


def _display_score(reserve, group_aisles, strong_neighbor=False):
    return round(_raw_score(reserve, group_aisles, strong_neighbor) * 100)


def _score_breakdown(reserve, group_aisles, strong_neighbor=False):
    terms = _score_terms(reserve, group_aisles, strong_neighbor)
    return {
        name: (None if value is None else round(value * 100))
        for name, (value, _) in zip(SCORE_PART_NAMES, terms)
    }


def _rail_score(reserve, group_aisles, strong_neighbor=False):
    tie_break = reserve.get("share_pct", 0) / TIE_BREAK_SHARE
    return _raw_score(reserve, group_aisles, strong_neighbor) + tie_break


def _choose_reserve_aisle(reserve_days, group_aisles, strong_neighbor=False):
    if not reserve_days:
        return None
    return max(reserve_days, key=lambda s: _rail_score(s, group_aisles, strong_neighbor))


def _weighted_companion_aisles(result):
    order_count_by_name = {
        c.get("name"): c.get("count", 0)
        for c in (result.get("companions") or [])
        if c.get("name")
    }
    return [
        (c["aisle"], order_count_by_name.get(c.get("name"), 0))
        for c in (result.get("companion_aisles") or [])
        if c.get("aisle")
    ]


def _enrich_full_location(
    result, used_cells=None, speed_rank=None, brain=None, group_aisles=None, strong_neighbor=False
):
    internal = result.get("_internal")
    heavy = weight.heavy(internal) if internal else None
    pick_aisle = result.get("aisle")
    if not pick_aisle:
        return
    companions = result.get("companions", [])

    own_refill = refill.for_item(internal) if internal else None
    if own_refill and own_refill.get("days"):
        reserve_days = _reserve_days_from_own(own_refill)
        result["by_own"] = True
        result["own_days"] = own_refill["days"]
    else:
        reserve_days = rmap.storage_for(pick_aisle)
    result["pick_aisle"] = pick_aisle

    companion_aisles = _weighted_companion_aisles(result)
    for reserve in reserve_days:
        reserve["_companion_aisles"] = companion_aisles

    group_at_choice = set(group_aisles) if group_aisles is not None else None
    chosen = _choose_reserve_aisle(reserve_days, group_aisles, strong_neighbor)

    fallback_r = (
        f"R{_aisle_num(pick_aisle):02d}" if _aisle_num(pick_aisle) is not None else pick_aisle
    )
    aisle = chosen["aisle"] if chosen else fallback_r
    result["aisle"] = aisle
    result["_reserve_days"] = reserve_days
    if group_aisles is not None:
        group_aisles.add(aisle)
    result["spread"] = chosen.get("spread") if chosen else None
    if chosen and "center" in chosen:
        result["serve_center"] = chosen["center"]

    aisle = _assign_cell(result, aisle, used_cells, speed_rank, heavy, reserve_days)
    result["aisle"] = aisle
    _build_candidates(
        result,
        reserve_days,
        aisle,
        companions,
        used_cells,
        speed_rank,
        heavy,
        group_at_choice,
        strong_neighbor,
    )


def _assign(result, aisle, cell, used_cells):
    result["zone"] = cell["zone"]
    result["cell"] = cell["code"]
    result["cell_floor"] = cell["floor"]
    result["floor"] = f"floor {cell['floor']}" if cell["floor"] is not None else "high floor"
    result["empties_in_aisle"] = cell["empties_in_aisle"]
    if used_cells is not None:
        used_cells.add(cell["code"])
    oc.mark_taken(cell["code"], result.get("_internal"))


def _assign_cell(result, aisle, used_cells, speed_rank, heavy, reserve_days=None):
    cell = oc.suggest_cell(aisle, used_cells, speed_rank, heavy)
    if cell:
        _assign(result, aisle, cell, used_cells)
        return aisle

    tried = {aisle}
    reserve_aisles = [r["aisle"] for r in (reserve_days or []) if r["aisle"] not in tried]
    base_num = _aisle_num(aisle)
    free_aisles = oc.free_reserve_aisles(used_cells)
    free_aisles.sort(
        key=lambda a: abs((_aisle_num(a) or FALLBACK_AISLE_DISTANCE) - (base_num or 0))
    )
    spillover = [a for a in free_aisles if a not in tried and a not in reserve_aisles]
    for fallback_aisle in reserve_aisles + spillover:
        cell = oc.suggest_cell(fallback_aisle, used_cells, speed_rank, heavy)
        if cell:
            _assign(result, fallback_aisle, cell, used_cells)
            result["moved_from"] = aisle
            return fallback_aisle

    result["zone"] = oc.zone_of(aisle)
    result["cell"] = None
    return aisle


def _build_candidates(
    result,
    reserve_days,
    aisle,
    companions,
    used_cells,
    speed_rank,
    heavy,
    group_aisles=None,
    strong_neighbor=False,
):
    comp_names = [c.get("name") for c in companions if c.get("name")][:TOP_COMP_NAMES]

    if not reserve_days:
        _fill_candidate_cells(result, used_cells, speed_rank, heavy)
        return

    best_per_aisle = _best_reserve_per_aisle(reserve_days, group_aisles, strong_neighbor)

    candidates = []
    for reserve in best_per_aisle.values():
        if reserve["aisle"] == aisle:
            continue
        cell = oc.suggest_cell(reserve["aisle"], used_cells, speed_rank, heavy)
        if not cell:
            continue
        if used_cells is not None:
            used_cells.add(cell["code"])
        candidates.append(
            {
                "aisle": reserve["aisle"],
                "cell": cell["code"],
                "share_pct": _display_score(reserve, group_aisles, strong_neighbor),
                "companions": comp_names,
            }
        )

    chosen_reserve = _chosen_reserve(
        best_per_aisle.get(aisle), reserve_days, aisle
    )
    candidates.insert(
        0,
        {
            "aisle": aisle,
            "cell": result.get("cell"),
            "share_pct": _display_score(chosen_reserve, group_aisles, strong_neighbor),
            "companions": comp_names,
        },
    )
    result["score_parts"] = _score_breakdown(chosen_reserve, group_aisles, strong_neighbor)
    candidates[1:] = sorted(candidates[1:], key=lambda c: -c["share_pct"])
    if len(candidates) > 1 and candidates[0]["share_pct"] < candidates[1]["share_pct"]:
        result["nhuong_day"] = candidates[1]["aisle"]
    result["candidates"] = candidates


def _best_reserve_per_aisle(reserve_days, group_aisles, strong_neighbor):
    best = {}
    for reserve in reserve_days:
        score = _rail_score(reserve, group_aisles, strong_neighbor)
        current = best.get(reserve["aisle"])
        if current is None or score > current[0]:
            best[reserve["aisle"]] = (score, reserve)
    return {aisle: reserve for aisle, (_, reserve) in best.items()}


def _chosen_reserve(chosen, reserve_days, aisle):
    if chosen:
        return chosen
    aisle_num = _aisle_num(aisle) or 0
    nearest = min(
        reserve_days, key=lambda r: abs((_aisle_num(r["aisle"]) or 0) - aisle_num)
    )
    offset = abs((_aisle_num(nearest["aisle"]) or 0) - aisle_num)
    return {**nearest, "aisle": aisle, "dist": nearest.get("dist", 0) + offset}


def _fill_candidate_cells(result, used_cells, speed_rank, heavy):
    for candidate in result.get("candidates", []):
        cell = oc.suggest_cell(candidate["aisle"], used_cells, speed_rank, heavy)
        if cell:
            candidate["cell"] = cell["code"]
            if used_cells is not None:
                used_cells.add(cell["code"])
        else:
            candidate["cell"] = candidate["aisle"]