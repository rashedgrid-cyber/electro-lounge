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


# ---------------------------------------------------------
# Power-industry relevance
# ---------------------------------------------------------

POWER_KEYWORDS = [
    "substation",
    "transformer",
    "switchgear",
    "transmission",
    "distribution",
    "electricity",
    "electrical",
    "solar",
    "photovoltaic",
    "renewable",
    "battery",
    "bess",
    "energy storage",
    "scada",
    "protection",
    "relay",
    "iec 61850",
    "hvdc",
    "facts",
    "cable",
    "overhead line",
    "ohtl",
    "power system",
    "power plant",
    "grid",
    "gis"
]

ARABIC_POWER_KEYWORDS = [
    "كهرباء",
    "كهربائي",
    "محطة كهرباء",
    "محطات كهرباء",
    "محول",
    "محولات",
    "نقل الكهرباء",
    "توزيع الكهرباء",
    "شبكة كهرباء",
    "شبكات الكهرباء",
    "طاقة شمسية",
    "طاقة متجددة",
    "طاقة الرياح",
    "محطة شمسية",
    "كابلات",
    "خطوط نقل"
]


# ---------------------------------------------------------
# Opportunity classification
# ---------------------------------------------------------

OPPORTUNITY_PATTERNS = {
    "ACTUAL_TENDER": [
        r"\btender\b",
        r"\btenders\b",
        r"\binvitation to bid\b",
        r"\binvitation for bid\b",
        r"\bcompetitive bidding\b",
        r"مناقصة",
        r"مناقصات",
        r"طرح مناقصة"
    ],

    "RFQ": [
        r"\brfq\b",
        r"\brequest for quotation\b",
        r"\brequest for quote\b",
        r"طلب عرض سعر",
        r"طلب عروض أسعار"
    ],

    "EOI": [
        r"\beoi\b",
        r"\bexpression of interest\b",
        r"إبداء اهتمام",
        r"ابداء اهتمام"
    ],

    "PREQUALIFICATION": [
        r"\bprequalification\b",
        r"\bpre-qualification\b",
        r"\bpre qualification\b",
        r"تأهيل مسبق",
        r"التأهيل المسبق"
    ],

    "VENDOR_REGISTRATION": [
        r"\bvendor registration\b",
        r"\bsupplier registration\b",
        r"\bcontractor registration\b",
        r"\bcontractor and vendor registration\b",
        r"تسجيل المورد",
        r"تسجيل الموردين",
        r"تسجيل المقاول",
        r"تسجيل المقاولين"
    ],

    "FUTURE_PROJECT": [
        r"\bfuture project\b",
        r"\bfuture projects\b",
        r"\bupcoming project\b",
        r"\bupcoming projects\b",
        r"\bplanned project\b",
        r"\bplanned projects\b",
        r"مشروعات مستقبلية",
        r"مشاريع مستقبلية"
    ]
}


# ---------------------------------------------------------
# Known informational/noise patterns
# ---------------------------------------------------------

INFORMATION_PATTERNS = [
    r"\buser guide\b",
    r"\bterms\s*&?\s*condition",
    r"\bterms and conditions\b",
    r"\blegislation\b",
    r"\bprocedures and guides\b",
    r"\bprocedure and guide\b",
    r"\bcertified contractors\b",
    r"\bcertified contractors and consultants\b",
    r"\bperformance evaluation\b",
    r"\bbid box locations\b",
    r"\blogistics details\b",
    r"\bsolar power unit\b",
    r"\bwind atlas\b",
    r"\bstatistics\b",
    r"دليل المستخدم",
    r"الشروط والأحكام",
    r"التشريعات",
    r"إحصائيات",
    r"اختبارات كفاءة",
    r"إختبارات كفاءة"
]


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

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


def contains_arabic(text):
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def phrase_match(text, phrase):
    """
    Match complete English words/phrases instead of substrings.

    This prevents:
        GIS matching registration
        GIS matching logistics
        PV matching unrelated longer words
    """

    text_lower = text.lower()
    phrase_lower = phrase.lower()

    pattern = (
        r"(?<![A-Za-z0-9])"
        + re.escape(phrase_lower)
        + r"(?![A-Za-z0-9])"
    )

    return bool(re.search(pattern, text_lower))


# ---------------------------------------------------------
# Power relevance
# ---------------------------------------------------------

def power_relevance(text):
    matched = []
    score = 0

    for keyword in POWER_KEYWORDS:
        if phrase_match(text, keyword):
            matched.append(keyword)
            score += 2

    for keyword in ARABIC_POWER_KEYWORDS:
        if keyword in text:
            matched.append(keyword)
            score += 2

    return score, sorted(set(matched))


# ---------------------------------------------------------
# Opportunity classification
# ---------------------------------------------------------

def classify_opportunity(title, url):
    searchable = f"{title} {url}".lower()

    # Strong business-opportunity classifications
    for classification, patterns in OPPORTUNITY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, searchable, re.IGNORECASE):
                return classification

    # Known informational pages
    for pattern in INFORMATION_PATTERNS:
        if re.search(pattern, searchable, re.IGNORECASE):
            return "INFORMATION_ONLY"

    return "INFORMATION_ONLY"


def opportunity_score(classification):
    weights = {
        "ACTUAL_TENDER": 10,
        "RFQ": 10,
        "EOI": 9,
        "PREQUALIFICATION": 8,
        "FUTURE_PROJECT": 7,
        "VENDOR_REGISTRATION": 6,
        "INFORMATION_ONLY": 0
    }

    return weights.get(classification, 0)


# ---------------------------------------------------------
# Source configuration
# ---------------------------------------------------------

def get_opportunity_sources(registry):
    sources = []

    for watcher in registry.get("watchers", []):
        if watcher.get("id") != "W02":
            continue

        for source in watcher.get("sources", []):
            if source.get("enabled", True):
                sources.append(source)

    return sources


# ---------------------------------------------------------
# Collection
# ---------------------------------------------------------

def collect_source(source):
    name = source.get("name", "Unknown Source")
    country = source.get("country")
    url = source.get("url")
    priority = source.get("priority", "medium")

    print()
    print(f"Checking: {name}")
    print(f"URL: {url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(compatible; ElectroLoungeOpportunityRadar/2.0)"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup([
        "script",
        "style",
        "noscript",
        "svg"
    ]):
        tag.decompose()

    items = []

    for link in soup.find_all("a", href=True):
        title = clean_text(
            link.get_text(" ", strip=True)
        )

        if len(title) < 5:
            continue

        absolute_url = urljoin(
            response.url,
            link.get("href")
        )

        classification = classify_opportunity(
            title,
            absolute_url
        )

        # Ignore ordinary informational/navigation links.
        if classification == "INFORMATION_ONLY":
            continue

        power_score, matched_power = power_relevance(
            f"{title} {absolute_url}"
        )

        business_score = opportunity_score(
            classification
        )

        # Vendor registration/prequalification/tenders may
        # themselves be useful even when the title does not
        # contain an electrical keyword, because the source is
        # already an approved power-industry organization.
        total_score = business_score + power_score

        arabic = contains_arabic(title)

        item = {
            "id": make_id(
                name,
                absolute_url,
                title
            ),

            "status": "NEW",

            "title": title,

            "country": country,

            "source": name,

            "source_priority": priority,

            "source_url": absolute_url,

            "source_page": response.url,

            "classification": classification,

            "business_score": business_score,

            "power_relevance_score": power_score,

            "relevance_score": total_score,

            "matched_power_keywords": matched_power,

            "discovered_at": datetime.now(
                timezone.utc
            ).isoformat(),

            "language": (
                "AR"
                if arabic
                else "EN"
            ),

            "translation_required": arabic,

            "approved": False,

            "verification_status": "UNVERIFIED",

            "publish_to_site": False,

            "publish_to_rss": False,

            "linkedin_candidate": False
        }

        items.append(item)

    return items


# ---------------------------------------------------------
# Deduplication
# ---------------------------------------------------------

def deduplicate(items):
    unique = {}

    for item in items:
        key = item["id"]

        if key not in unique:
            unique[key] = item

    return list(unique.values())


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    print(
        "Electro Lounge Opportunity Radar V2"
    )

    print(
        "==================================="
    )

    registry = load_json(REGISTRY_FILE)

    if not registry:
        raise FileNotFoundError(
            f"Registry not found: {REGISTRY_FILE}"
        )

    sources = get_opportunity_sources(registry)

    print(
        f"Enabled W02 sources: {len(sources)}"
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    existing = load_json(
        OUTPUT_FILE,
        default={
            "project": "Electro Lounge",
            "opportunities": []
        }
    )

    existing_items = existing.get(
        "opportunities",
        []
    )

    # V2 rebuilds the candidate list from current
    # source results instead of preserving V1 noise.
    collected_items = []

    source_results = []

    for source in sources:
        source_name = source.get(
            "name",
            "Unknown Source"
        )

        try:
            items = collect_source(source)

            collected_items.extend(items)

            source_results.append({
                "source": source_name,
                "status": "SUCCESS",
                "items_found": len(items)
            })

            print(
                f"Candidates found: {len(items)}"
            )

        except Exception as exc:
            print(
                f"ERROR reading {source_name}: {exc}"
            )

            source_results.append({
                "source": source_name,
                "status": "ERROR",
                "error": str(exc),
                "items_found": 0
            })

    collected_items = deduplicate(
        collected_items
    )

    # Preserve approval/verification state when the
    # same opportunity already existed previously.
    existing_by_id = {
        item.get("id"): item
        for item in existing_items
        if item.get("id")
    }

    for item in collected_items:
        old = existing_by_id.get(
            item["id"]
        )

        if not old:
            continue

        item["approved"] = old.get(
            "approved",
            False
        )

        item["verification_status"] = old.get(
            "verification_status",
            "UNVERIFIED"
        )

        item["publish_to_site"] = old.get(
            "publish_to_site",
            False
        )

        item["publish_to_rss"] = old.get(
            "publish_to_rss",
            False
        )

        item["linkedin_candidate"] = old.get(
            "linkedin_candidate",
            False
        )

    collected_items.sort(
        key=lambda item: (
            item.get(
                "relevance_score",
                0
            ),
            item.get(
                "source_priority"
            ) == "high"
        ),
        reverse=True
    )

    collected_items = collected_items[
        :MAX_ITEMS
    ]

    counts = {}

    for item in collected_items:
        classification = item.get(
            "classification",
            "UNKNOWN"
        )

        counts[classification] = (
            counts.get(
                classification,
                0
            ) + 1
        )

    previous_ids = {
        item.get("id")
        for item in existing_items
        if item.get("id")
    }

    new_count = sum(
        1
        for item in collected_items
        if item.get("id") not in previous_ids
    )

    output = {
        "project": "Electro Lounge",

        "watcher": "W02",

        "version": "2.0",

        "name": (
            "Tender RFQ and Project Radar"
        ),

        "markets": [
            "Saudi Arabia",
            "Egypt"
        ],

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "source_count": len(sources),

        "source_results": source_results,

        "new_opportunities_this_run": (
            new_count
        ),

        "opportunity_count": len(
            collected_items
        ),

        "classification_counts": counts,

        "opportunities": collected_items
    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )

    print()
    print(
        "==================================="
    )

    print(
        f"Stored opportunities: "
        f"{len(collected_items)}"
    )

    print(
        f"New opportunities: {new_count}"
    )

    print(
        f"Classifications: {counts}"
    )

    print(
        f"Saved to: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
