import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

import feedparser

BASE = Path(__file__).resolve().parents[1]
CONFIG = BASE / "config" / "rss-sources.json"
OUTPUT = BASE / "data" / "rss-candidates.json"

MAX_ITEMS_PER_FEED = 20
MAX_STORED = 200


def make_id(source, link, title):
    raw = f"{source}|{link}|{title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def load_sources():
    with open(CONFIG, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Supports either a plain list or {"sources": [...]}
    if isinstance(data, list):
        return data

    return data.get("sources", [])


def main():
    sources = load_sources()
    candidates = []

    for source in sources:
        name = source.get("name", "Unknown")
        url = source.get("url") or source.get("feed_url")

        if not url:
            continue

        try:
            feed = feedparser.parse(url)

            for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()

                if not title or not link:
                    continue

                candidates.append({
                    "id": make_id(name, link, title),
                    "title": title,
                    "source": name,
                    "category": source.get("category", "Power Industry"),
                    "source_priority": source.get("priority", "normal"),
                    "source_url": link,
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", ""),
                    "status": "NEW",
                    "approved": False,
                    "electro_lounge_article": None,
                    "electro_lounge_image": None
                })

        except Exception as exc:
            print(f"ERROR reading {name}: {exc}")

    # Deduplicate
    unique = {}
    for item in candidates:
        unique[item["id"]] = item

    candidates = list(unique.values())[:MAX_STORED]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "project": "Electro Lounge",
        "system": "RSS Idea Radar",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Internal RSS idea radar. Source links are retained for verification and traceability.",
        "candidate_count": len(candidates),
        "candidates": candidates
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Electro Lounge RSS Radar completed: {len(candidates)} candidates")


if __name__ == "__main__":
    main()
