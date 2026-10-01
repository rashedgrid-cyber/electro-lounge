import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, timezone
from html import unescape

import feedparser


CONFIG_FILE = Path("config/rss-sources.json")
OUTPUT_FILE = Path("data/rss-candidates.json")

# Keep the radar manageable.
MAX_ITEMS_PER_SOURCE = 20
MAX_TOTAL_CANDIDATES = 150


def load_json(path, default=None):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def clean_text(value):
    """Remove simple HTML and normalize whitespace."""
    if not value:
        return ""

    value = unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def make_id(source_name, link, title):
    """Create a stable unique ID for duplicate detection."""
    raw = f"{source_name}|{link}|{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def relevance_score(title, summary, preferred_topics):
    """
    Simple zero-cost keyword scoring.

    AI scoring can be added later after we verify
    that the RSS collection itself works correctly.
    """
    text = f"{title} {summary}".lower()

    score = 0
    matched_topics = []

    for topic in preferred_topics:
        topic_lower = topic.lower()

        if topic_lower in text:
            score += 2
            matched_topics.append(topic)

        # Also look at individual meaningful words.
        words = [
            word
            for word in re.findall(r"[a-zA-Z0-9]+", topic_lower)
            if len(word) >= 4
        ]

        word_matches = sum(
            1 for word in words
            if re.search(rf"\b{re.escape(word)}\b", text)
        )

        if word_matches:
            score += min(word_matches, 2)

    return score, sorted(set(matched_topics))


def get_published(entry):
    """Return the source publication date when available."""
    if entry.get("published"):
        return clean_text(entry.get("published"))

    if entry.get("updated"):
        return clean_text(entry.get("updated"))

    return ""


def main():
    print("Electro Lounge RSS Radar")
    print("========================")

    config = load_json(CONFIG_FILE)

    if not config:
        raise FileNotFoundError(
            f"Configuration file not found: {CONFIG_FILE}"
        )

    sources = config.get("sources", [])
    preferred_topics = config.get("preferred_topics", [])

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    existing_data = load_json(
        OUTPUT_FILE,
        default={
            "project": "Electro Lounge",
            "generated_at": None,
            "candidates": []
        }
    )

    existing_candidates = existing_data.get("candidates", [])

    # IDs already collected in earlier runs.
    known_ids = {
        candidate.get("id")
        for candidate in existing_candidates
        if candidate.get("id")
    }

    new_candidates = []

    for source in sources:
        source_name = source.get("name", "Unknown Source")
        category = source.get("category", "General")
        priority = source.get("priority", "medium")
        feed_url = source.get("feed")

        if not feed_url:
            continue

        print(f"\nChecking: {source_name}")
        print(f"Feed: {feed_url}")

        try:
            feed = feedparser.parse(feed_url)

            if getattr(feed, "bozo", False):
                print(
                    "Warning: feed parser reported:",
                    getattr(feed, "bozo_exception", "Unknown feed issue")
                )

            entries = feed.entries[:MAX_ITEMS_PER_SOURCE]

            print(f"Items found: {len(entries)}")

            for entry in entries:
                title = clean_text(entry.get("title", ""))
                link = clean_text(entry.get("link", ""))
                summary = clean_text(
                    entry.get("summary")
                    or entry.get("description")
                    or ""
                )

                if not title:
                    continue

                candidate_id = make_id(
                    source_name,
                    link,
                    title
                )

                if candidate_id in known_ids:
                    continue

                score, matched_topics = relevance_score(
                    title,
                    summary,
                    preferred_topics
                )

                # For the first test we retain every item,
                # but score it so we can inspect what the feeds produce.
                candidate = {
                    "id": candidate_id,
                    "status": "NEW",
                    "title": title,
                    "summary": summary[:1200],
                    "source": source_name,
                    "source_category": category,
                    "source_priority": priority,
                    "source_url": link,
                    "published": get_published(entry),
                    "relevance_score": score,
                    "matched_topics": matched_topics,
                    "discovered_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "approved": False,
                    "electro_lounge_article": None,
                    "electro_lounge_image": None
                }

                new_candidates.append(candidate)
                known_ids.add(candidate_id)

        except Exception as exc:
            # One bad RSS feed should not stop the entire radar.
            print(f"ERROR reading {source_name}: {exc}")

    # Higher-scoring candidates appear first.
    new_candidates.sort(
        key=lambda item: (
            item.get("relevance_score", 0),
            item.get("source_priority") == "high"
        ),
        reverse=True
    )

    combined = new_candidates + existing_candidates
    combined = combined[:MAX_TOTAL_CANDIDATES]

    output = {
        "project": "Electro Lounge",
        "purpose": (
            "Internal RSS idea radar. Source links are retained "
            "for verification and traceability."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "new_candidates_this_run": len(new_candidates),
        "candidate_count": len(combined),
        "candidates": combined
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("\n========================")
    print(f"New candidates: {len(new_candidates)}")
    print(f"Stored candidates: {len(combined)}")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
