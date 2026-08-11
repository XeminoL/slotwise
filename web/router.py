from data import loader


def diagnose(files):
    pick_bytes = None
    location_aisle, aisle_capacity = {}, {}
    name, category, alias = {}, {}, {}

    for fname, raw in files:
        kind = loader.classify_file(raw)
        if kind == "pick" and pick_bytes is None:
            pick_bytes = raw
        elif kind == "location":
            aisle_map, capacity = loader.load_locations(raw)
            location_aisle.update(aisle_map)
            aisle_capacity.update(capacity)
        elif kind == "product":
            names, cats, aliases = loader.load_products(raw)
            name.update(names)
            category.update(cats)
            alias.update(aliases)

    return {
        "pick_bytes": pick_bytes,
        "location_aisle": location_aisle,
        "aisle_capacity": aisle_capacity,
        "name": name,
        "category": category,
        "alias": alias,
    }