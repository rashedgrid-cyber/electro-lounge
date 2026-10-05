import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote_plus

REGISTRY_FILE = Path("config/source-registry.json")
OUTPUT_FILE = Path("data/intelligence-candidates.json")
MAX_ITEMS = 300


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def make_id(watcher, source, title):
    raw = f"{watcher}|{source}|{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def get_watcher(registry, watcher_id):
    for watcher in registry.get("watchers", []):
        if watcher.get("id") == watcher_id:
            return watcher
    return None


def google_news_rss(query):
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en&gl=US&ceid=US:en"
    )


def build_w04(watcher):
    candidates = []

    manufacturers = watcher.get("manufacturers", [])
    topics = watcher.get("topics", [])

    # Group topics to avoid excessive queries.
    priority_topics = [
        "transformer",
        "GIS",
        "digital substation",
        "HVDC",
        "BESS",
        "IEC 61850"
    ]

    for manufacturer in manufacturers:
        if not manufacturer.get("enabled", True):
            continue

        name = manufacturer.get("name")

        for topic in priority_topics:
            if topic not in topics:
                continue

            query = f'"{name}" "{topic}"'

            candidates.append({
                "id": make_id("W04", name, query),
                "watcher": "W04",
                "category": "MANUFACTURER_PRODUCT",
                "manufacturer": name,
                "topic": topic,
                "query": query,
                "discovery_feed": google_news_rss(query),
                "scope": "GLOBAL",
                "status": "READY_FOR_DISCOVERY",
                "approved": False
            })

    return candidates


def build_w05(watcher):
    candidates = []

    topics = watcher.get("topics", [])

    for topic in topics:
        query = f'"{topic}" electricity OR utility OR grid'

        candidates.append({
            "id": make_id("W05", "emerging-tech", query),
            "watcher": "W05",
            "category": "STARTUP_TECH",
            "topic": topic,
            "query": query,
            "discovery_feed": google_news_rss(query),
            "scope": "GLOBAL",
            "status": "READY_FOR_DISCOVERY",
            "approved": False
        })

    return candidates


def build_w06(watcher):
    candidates = []

    entities = watcher.get("monitor_entities", [])
    topics = watcher.get("topics", [])

    priority_topics = [
        "new product",
        "project award",
        "substation",
        "transformer",
        "GIS",
        "HVDC",
        "BESS"
    ]

    for entity in entities:
        # Generic entity groups are handled later by n8n.
        if entity in [
            "utilities",
            "transmission operators",
            "project developers",
            "renewable developers",
            "government energy organizations"
        ]:
            continue

        for topic in priority_topics:
            if topic not in topics:
                continue

            # Public web discovery only.
            # We do not scrape X/Facebook directly.
            query = (
                f'"{entity}" "{topic}" '
                f'(site:x.com OR site:facebook.com)'
            )

            candidates.append({
                "id": make_id("W06", entity, query),
                "watcher": "W06",
                "category": "SOCIAL_RELEASE",
                "entity": entity,
                "topic": topic,
                "platforms": ["X", "Facebook"],
                "query": query,
                "discovery_feed": google_news_rss(query),
                "scope": "GLOBAL",
                "status": "READY_FOR_DISCOVERY",
                "verification_required": True,
                "approved": False
            })

    return candidates


def deduplicate(items):
    unique = {}

    for item in items:
        unique[item["id"]] = item

    return list(unique.values())


def main():
    print("Electro Lounge Intelligence Radar")
    print("=================================")

    registry = load_json(REGISTRY_FILE)

    all_candidates = []

    counts = {}

    for watcher_id, builder in [
        ("W04", build_w04),
        ("W05", build_w05),
        ("W06", build_w06)
    ]:
        watcher = get_watcher(registry, watcher_id)

        if not watcher:
            print(f"{watcher_id}: not found")
            counts[watcher_id] = 0
            continue

        if not watcher.get("enabled", True):
            print(f"{watcher_id}: disabled")
            counts[watcher_id] = 0
            continue

        items = builder(watcher)

        all_candidates.extend(items)
        counts[watcher_id] = len(items)

        print(
            f"{watcher_id} "
            f"{watcher.get('name')}: "
            f"{len(items)} discovery targets"
        )

    all_candidates = deduplicate(all_candidates)

    all_candidates = all_candidates[:MAX_ITEMS]

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output = {
        "project": "Electro Lounge",
        "system": "Shared Intelligence Radar",
        "watchers": ["W04", "W05", "W06"],
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "counts": counts,
        "candidate_count": len(all_candidates),
        "note": (
            "Discovery targets only. Results require "
            "collection, verification and human approval."
        ),
        "candidates": all_candidates
    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("---------------------------------")
    print(f"Counts: {counts}")
    print(
        f"Total discovery targets: "
        f"{len(all_candidates)}"
    )
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
