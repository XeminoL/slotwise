import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ortools.sat.python import cp_model

from core import brain as brain_mod

NUM_ITEMS = 120
MAX_SECONDS = 30.0
UNLIMITED_CAPACITY = 10**6


def _collect_candidates(brain, item_list):
    """For each item, takes the list of (aisle, score) from the heuristic itself.

    The score comes from the share_pct field of place(), the same scale the
    heuristic ranks by, so the comparison does not change the objective.
    """
    candidates = {}
    chosen = {}
    for item in item_list:
        result = brain_mod.place(brain, item)
        ds = result.get("candidates") or []
        valid = [(c["aisle"], int(c.get("share_pct", 0)))
                 for c in ds if c.get("aisle")]
        if not valid:
            continue
        candidates[item] = valid
        chosen[item] = result.get("aisle")
    return candidates, chosen


def solve_cp_sat(candidates, capacity):
    """Assigns items to aisles for the highest total score, respecting capacity."""
    model = cp_model.CpModel()
    var = {}

    for item, ds in candidates.items():
        for aisle, _ in ds:
            var[(item, aisle)] = model.NewBoolVar(f"x_{item}_{aisle}")
        model.AddExactlyOne(var[(item, aisle)] for aisle, _ in ds)

    all_aisles = {aisle for ds in candidates.values() for aisle, _ in ds}
    for aisle in all_aisles:
        in_aisle = [var[(item, a)] for item, ds in candidates.items()
                    for a, _ in ds if a == aisle]
        if in_aisle:
            model.Add(sum(in_aisle) <= capacity.get(aisle, len(in_aisle)))

    model.Maximize(
        sum(score * var[(item, aisle)]
            for item, ds in candidates.items() for aisle, score in ds)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = MAX_SECONDS
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    assignment = {}
    for (item, aisle), b in var.items():
        if solver.Value(b):
            assignment[item] = aisle
    return {
        "assignment": assignment,
        "objective": int(solver.ObjectiveValue()),
        "status": solver.StatusName(status),
        "wall_time": round(solver.WallTime(), 2),
    }


def score_of_current_approach(candidates, chosen):
    """Total score when taking the aisle the heuristic suggested."""
    total = 0
    for item, ds in candidates.items():
        aisle = chosen.get(item)
        for a, score in ds:
            if a == aisle:
                total += score
                break
    return total


def count_by_aisle(assignment):
    from collections import Counter
    return Counter(assignment.values())


def main():
    brain = brain_mod.load()
    if brain is None:
        print("No brain.pkl yet. Run tools/retrain.py first.")
        return

    item_list = list(brain["advice"])[:NUM_ITEMS]
    candidates, chosen = _collect_candidates(brain, item_list)
    if not candidates:
        print("No candidates returned.")
        return

    all_aisles = sorted({aisle for ds in candidates.values() for aisle, _ in ds})
    current_score = score_of_current_approach(candidates, chosen)
    heuristic_spread = count_by_aisle(chosen)
    busiest = max(heuristic_spread.values())

    print(f"items                             : {len(candidates)}")
    print(f"candidate aisles                  : {len(all_aisles)}")
    print(f"most the heuristic put in one aisle: {busiest}")
    print()

    # Round 1: no capacity limit on either side, so this measures aisle choice alone.
    result_free = solve_cp_sat(
        candidates, {a: UNLIMITED_CAPACITY for a in all_aisles})

    # Round 2: same capacity limit on both sides.
    cap = busiest
    result_capped = solve_cp_sat(candidates, {a: cap for a in all_aisles})

    print(f"{'comparison':<34}{'Heuristic':>11}{'CP-SAT':>11}{'gap':>10}")
    print("-" * 66)

    if result_free:
        gap = (result_free["objective"] - current_score) / result_free["objective"] * 100
        print(f"{'no capacity limit':<34}{current_score:>11,}"
              f"{result_free['objective']:>11,}{gap:>9.1f}%")

    if result_capped:
        gap = (result_capped["objective"] - current_score) / result_capped["objective"] * 100
        print(f"{'capacity ' + str(cap) + ' per aisle':<34}{current_score:>11,}"
              f"{result_capped['objective']:>11,}{gap:>9.1f}%")

    print()
    if result_free:
        diff = sum(1 for item, aisle in result_free["assignment"].items()
                   if chosen.get(item) != aisle)
        print(f"CP-SAT (no limit) placed differently from the heuristic: "
              f"{diff} / {len(result_free['assignment'])} items")
        print(f"solve time: {result_free['wall_time']}s, "
              f"status {result_free['status']}")

    print()
    print("How to read this: the heuristic does not cap capacity when it picks an")
    print("aisle, so only the first row compares like with like. The second row shows")
    print("the score lost when items have to spread across more aisles.")


if __name__ == "__main__":
    main()
