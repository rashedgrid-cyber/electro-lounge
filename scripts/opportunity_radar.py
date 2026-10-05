import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

REGISTRY_FILE = Path("config/source-registry.json")
OUTPUT_FILE = Path("data/opportunities.json")
TIMEOUT = 25
MAX_ITEMS = 200

POWER_KEYWORDS = [
    "substation", "transformer", "switchgear", "gis",
    "transmission", "distribution", "power", "electricity",
    "electrical", "solar", "photovoltaic", "pv", "wind",
    "renewable", "battery", "bess", "energy storage",
    "scada", "protection", "relay", "iec 61850",
    "hvdc", "facts", "cable", "overhead line", "ohtl",
    "tender", "rfq", "request for quotation", "procurement",
    "contract", "bid", "project", "vendor", "supplier",
    "prequalification"
]

ARABIC_KEYWORDS = [
    "كهرباء", "كهربائي", "محطة", "محطات", "محول", "محولات",
    "نقل الكهرباء", "شبكة", "شبكات", "طاقة", "طاقة شمسية",
    "طاقة متجددة", "مناقصة", "مناقصات", "توريد", "مورد",
    "موردين", "تأهيل", "مشروع", "مشروعات"
]


def load_json(path, default=None):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def clean_text(value):
    if not value:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()


def make_id(source, url, title):
    raw = f"{source}|{url}|{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def relevance_score(text):
    text_lower = text.lower()
    matched = []
    score = 0

    for keyword in POWER_KEYWORDS:
        if keyword.lower() in text_lower:
            matched.append(keyword)
            score += 2

    for keyword in ARABIC_KEYWORDS:
        if keyword in text:
            matched.append(keyword)
            score += 2

    return score, sorted(set(matched))


def get_opportunity_sources(registry):
    sources = []

    for watcher in registry.get("watchers", []):
        if watcher.get("id") != "W02":
            continue

        for source in watcher.get("sources", []):
            if source.get("enabled", True):
                sources.append(source)

    return sources


def collect_source(source):
    name = source.get("name", "Unknown Source")
    country = source.get("country")
    url = source.get("url")
    priority = source.get("priority", "medium")

    print(f"\nChecking: {name}")
    print(f"URL: {url}")

    headers = {
        "User-Agent": "Mozilla/5.0 Electro-Lounge-Opportunity-Radar/1.0"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=TIMEOUT
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    items = []

    for link in soup.find_all("a", href=True):
        title = clean_text(link.get_text(" ", strip=True))

        if len(title) < 5:
            continue

        absolute_url = urljoin(response.url, link.get("href"))

        score, matched_keywords = relevance_score(title)

        if score == 0:
            continue

        arabic = bool(re.search(r"[\u0600-\u06FF]", title))

        items.append({
            "id": make_id(name, absolute_url, title),
            "status": "NEW",
            "title": title,
            "country": country,
            "source": name,
            "source_priority": priority,
            "source_url": absolute_url,
            "source_page": response.url,
            "relevance_score": score,
            "matched_keywords": matched_keywords,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "language": "AR" if arabic else "EN",
            "translation_required": arabic,
            "classification": ["OPPORTUNITY"],
            "approved": False
        })

    return items


def main():
    print("Electro Lounge Opportunity Radar")
    print("================================")

    registry = load_json(REGISTRY_FILE)

    if not registry:
        raise FileNotFoundError(
            f"Registry not found: {REGISTRY_FILE}"
        )

    sources = get_opportunity_sources(registry)

    print(f"Enabled W02 sources: {len(sources)}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    existing = load_json(
        OUTPUT_FILE,
        default={
            "project": "Electro Lounge",
            "opportunities": []
        }
    )

    existing_items = existing.get("opportunities", [])

    known_ids = {
        item.get("id")
        for item in existing_items
        if item.get("id")
    }

    new_items = []

    for source in sources:
        try:
            collected = collect_source(source)

            for item in collected:
                if item["id"] in known_ids:
                    continue

                new_items.append(item)
                known_ids.add(item["id"])

        except Exception as exc:
            # One unavailable source must not stop the whole radar.
            print(f"ERROR reading {source.get('name')}: {exc}")

    unique = {
        item["id"]: item
        for item in new_items
    }

    new_items = list(unique.values())

    new_items.sort(
        key=lambda item: (
            item.get("relevance_score", 0),
            item.get("source_priority") == "high"
        ),
        reverse=True
    )

    combined = (new_items + existing_items)[:MAX_ITEMS]

    output = {
        "project": "Electro Lounge",
        "watcher": "W02",
        "name": "Tender RFQ and Project Radar",
        "markets": ["Saudi Arabia", "Egypt"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "new_opportunities_this_run": len(new_items),
        "opportunity_count": len(combined),
        "opportunities": combined
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("================================")
    print(f"New opportunities: {len(new_items)}")
    print(f"Stored opportunities: {len(combined)}")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
