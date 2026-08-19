import re
from itertools import permutations

GATE = 0
MAX_TSP_STOPS = 9


def _aisle_num(aisle_code):
    m = re.match(r"^[A-Za-z]+(\d+)$", aisle_code or "")
    return int(m.group(1)) if m else None


def distance_one_way(aisles):
    nums = [n for n in (_aisle_num(a) for a in aisles) if n is not None]
    if not nums:
        return 0
    return 2 * (max(nums) - GATE)


def distance_tsp(aisles):
    nums = sorted({n for n in (_aisle_num(a) for a in aisles) if n is not None})
    if not nums:
        return 0
    if len(nums) > MAX_TSP_STOPS:
        return distance_one_way(aisles)

    best = None
    for order in permutations(nums):
        total = abs(order[0] - GATE)
        for a, b in zip(order, order[1:]):
            total += abs(b - a)
        total += abs(order[-1] - GATE)
        if best is None or total < best:
            best = total
    return best


def measure_order(aisles):
    nums = sorted({n for n in (_aisle_num(a) for a in aisles) if n is not None})
    if not nums:
        return None
    return {
        "aisles": len(nums),
        "span": nums[-1] - nums[0],
        "one_way": distance_one_way(aisles),
        "tsp": distance_tsp(aisles),
        "sequence": nums,
    }


def measure_orders(orders, aisle_of_item):
    total = {"aisles": 0, "span": 0, "one_way": 0, "tsp": 0}
    count = 0
    for item_set in orders.values():
        aisles = [aisle_of_item[i] for i in item_set if i in aisle_of_item]
        result = measure_order(aisles)
        if not result:
            continue
        for k in total:
            total[k] += result[k]
        count += 1
    if not count:
        return None
    return {k: round(v / count, 3) for k, v in total.items()} | {"orders": count}
