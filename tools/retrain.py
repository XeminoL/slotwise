import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import brain as brain_mod
from data import loader
from data import warehouse
from web import router

UNLIMITED_CAPACITY = 10**9
REQUIRED_ROLES = ("pick", "location", "product")


def _read_file(role):
    p = warehouse.WAREHOUSE_DIR / warehouse.ROLE_FILES[role]
    if not p.exists():
        raise SystemExit(f"Missing file {p}. Upload the data through the web app first.")
    return p.name, p.read_bytes()


def main():
    t0 = time.time()
    print("Reading loaded data...")
    named = [_read_file(v) for v in REQUIRED_ROLES]
    for name, raw in named:
        print(f"  {name:<28} {len(raw) / 1e6:>8.1f} MB")

    print()
    print("Detecting columns...")
    diagnosis = router.diagnose(named)
    print(f"  aisles detected  : {len(diagnosis['location_aisle']):,} locations")
    print(f"  capacity         : {len(diagnosis['aisle_capacity'] or {})} aisles")

    print()
    print("Reading pick history...")
    orders, frequency, current_aisles = loader.load_pick_history(
        diagnosis["pick_bytes"], diagnosis["location_aisle"], log=lambda m: print(f"  {m}")
    )
    print(f"  orders       : {len(orders):,}")
    print(f"  items        : {len(frequency):,}")

    print()
    print("Training...")
    brain = brain_mod.build(
        orders,
        frequency,
        current_aisles,
        diagnosis["aisle_capacity"] or {"A1": UNLIMITED_CAPACITY},
        diagnosis.get("name", {}),
        diagnosis.get("category", {}),
        log=lambda m: print(f"  {m}"),
    )
    brain["alias"] = diagnosis.get("alias", {})
    brain_mod.save(brain)

    s = brain["stats"]
    bt = s.get("backtest", {})
    print()
    print("=" * 58)
    print(f"  orders trained on      : {s.get('orders', 0):,}")
    print(f"  items                  : {s.get('items', 0):,}")
    print(f"  cluster purity         : {s.get('purity', 0)}%")
    print(f"  aisles per order before: {bt.get('before')}")
    print(f"  aisles per order after : {bt.get('after')}")
    print(f"  reduction              : {bt.get('reduction')}%")
    print(f"  with current_aisle     : "
          f"{sum(1 for a in brain['advice'].values() if a.get('current_aisle')):,}"
          f" / {len(brain['advice']):,}")
    print(f"  elapsed                : {time.time() - t0:.0f}s")
    print("=" * 58)


if __name__ == "__main__":
    main()
