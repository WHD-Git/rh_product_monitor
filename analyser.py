import csv
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from downloader import DELIMITER, open_feed

REPORTS_DIR = Path(__file__).parent / "data" / "reports"

DESCRIPTION_MARKER = "Hamper contents include :"
DESC_MIN_CHARS = 10
DESC_SHORT_WORDS = 150
DESC_LONG_WORDS = 300


def _department_from_url(url: str) -> str:
    try:
        path = urlparse(url).path.strip("/")
        segment = path.split("/")[0]
        return segment if segment else "unknown"
    except Exception:
        return "unknown"


def _parse_price(raw: str) -> float | None:
    cleaned = raw.strip().split(" ")[0].replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _assess_description(desc: str) -> dict:
    marker = DESCRIPTION_MARKER.lower()
    idx = desc.lower().find(marker)
    pre_text = desc[:idx].strip() if idx != -1 else desc.strip()

    cleaned = re.sub(r"[^\w\s]", "", pre_text, flags=re.UNICODE).strip()
    words = cleaned.split()
    word_count = len(words)
    char_count = len(cleaned.replace(" ", ""))

    if char_count < DESC_MIN_CHARS:
        quality = "missing"
    elif word_count < DESC_SHORT_WORDS:
        quality = "short"
    elif word_count <= DESC_LONG_WORDS:
        quality = "good"
    else:
        quality = "long"

    return {"pre_text": pre_text, "word_count": word_count, "quality": quality}


def analyse(feed_path: Path) -> dict:
    date_str = feed_path.stem.replace("feed_", "")

    total_rows = 0
    parent_ids: set[str] = set()
    ids: set[str] = set()
    urls: list[str] = []
    dept_url_counts: Counter = Counter()

    # Per unique-id description tracking
    seen_id_for_desc: set[str] = set()
    id_details: list[dict] = []
    parent_desc_data: dict[str, dict] = {}       # for cross-parent duplicate detection
    family_pre_texts: dict[str, set] = {}        # family_id → set of distinct non-missing pre_texts
    desc_quality: Counter = Counter()
    missing_family_ids: list[str] = []

    # Department pricing (deduplicated by id+dept pair)
    seen_id_dept: set[tuple] = set()
    dept_prices: dict[str, list[float]] = {}

    # Family examples: first title + URL seen per family_id (used by comparator)
    family_examples: dict[str, dict] = {}
    # First non-occasion URL per family (preferred example for description issue tabs)
    family_generic_url: dict[str, str] = {}

    prices: list[float] = []
    no_price_ids: list[str] = []
    sale_price_count = 0
    availability_counts: Counter = Counter()
    occasion_counts: Counter = Counter()
    is_occasion_count = 0

    with open_feed(feed_path) as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        for row in reader:
            total_rows += 1
            pid = row.get("parent_id", "").strip()
            rid = row.get("id", "").strip()
            title = row.get("title", "").strip()
            desc = row.get("description", "").strip()
            link = row.get("link", "").strip()
            price_raw = row.get("price", "").strip()
            sale_raw = row.get("sale_price", "").strip()
            avail = row.get("availability", "").strip().lower()
            is_occasion = row.get("occasion product", "").strip().lower()
            occasion_type = row.get("specific occasion", "").strip()

            effective_pid = rid if pid == "-" or not pid else pid

            parent_ids.add(effective_pid)
            if rid:
                ids.add(rid)

            dept = _department_from_url(link) if link else None
            if link and dept:
                urls.append(link)
                dept_url_counts[dept] += 1

            # Family example: store first title + URL seen per family
            if effective_pid not in family_examples and title and link:
                family_examples[effective_pid] = {"title": title, "url": link}

            # Prefer first non-occasion URL as the "generic" example
            if link and effective_pid not in family_generic_url and is_occasion not in ("true", "1", "yes"):
                family_generic_url[effective_pid] = link

            price = _parse_price(price_raw)
            if price is not None:
                prices.append(price)
                # Department pricing deduplicated per (id, dept) pair
                if rid and dept:
                    key = (rid, dept)
                    if key not in seen_id_dept:
                        seen_id_dept.add(key)
                        dept_prices.setdefault(dept, []).append(price)
            else:
                no_price_ids.append(rid)

            if sale_raw and _parse_price(sale_raw) is not None:
                sale_price_count += 1

            if avail:
                availability_counts[avail] += 1

            if is_occasion in ("true", "1", "yes"):
                is_occasion_count += 1
            if occasion_type:
                occasion_counts[occasion_type] += 1

            # Assess description once per unique id
            if rid and rid not in seen_id_for_desc:
                seen_id_for_desc.add(rid)
                assessed = _assess_description(desc)
                quality = assessed["quality"]
                desc_quality[quality] += 1

                if quality == "missing":
                    missing_family_ids.append(effective_pid)

                id_details.append({
                    "family_id": effective_pid,
                    "id": rid,
                    "quality": quality,
                    "word_count": assessed["word_count"],
                    "pre_text_snippet": assessed["pre_text"][:150],
                })

                # Track distinct pre_texts per family for consistency check
                if quality != "missing" and assessed["pre_text"]:
                    family_pre_texts.setdefault(effective_pid, set()).add(assessed["pre_text"])

                # Cross-parent duplicate detection (first id per parent wins)
                if effective_pid not in parent_desc_data:
                    parent_desc_data[effective_pid] = {
                        "pre_text": assessed["pre_text"],
                        "quality": quality,
                    }

    # Enrich id_details with one example URL per family
    for item in id_details:
        fid = item["family_id"]
        item["example_url"] = family_generic_url.get(fid) or family_examples.get(fid, {}).get("url", "")

    # Department stats with pricing
    dept_stats: dict[str, dict] = {}
    for dept, count in dept_url_counts.most_common():
        dept_price_list = dept_prices.get(dept, [])
        dept_stats[dept] = {
            "url_count": count,
            "price_mean": round(statistics.mean(dept_price_list), 2) if dept_price_list else None,
            "price_median": round(statistics.median(dept_price_list), 2) if dept_price_list else None,
        }

    # Cross-parent duplicates: same non-missing pre_text across different family_ids
    pre_text_to_families: dict[str, list[str]] = {}
    for fid, data in parent_desc_data.items():
        if data["quality"] != "missing" and data["pre_text"]:
            pre_text_to_families.setdefault(data["pre_text"], []).append(fid)

    cross_parent_duplicates = [
        {
            "pre_text": pt[:120],
            "family_id_count": len(fids),
            "family_ids": fids[:10],
            "example_url": family_generic_url.get(fids[0]) or family_examples.get(fids[0], {}).get("url", ""),
        }
        for pt, fids in sorted(pre_text_to_families.items(), key=lambda x: -len(x[1]))
        if len(fids) > 1
    ][:10]

    # Intra-family description inconsistencies
    family_description_issues = sorted(
        [
            {
                "family_id": fid,
                "distinct_description_count": len(pre_texts),
                "pre_text_samples": [pt[:150] for pt in list(pre_texts)[:3]],
                "example_url": family_generic_url.get(fid) or family_examples.get(fid, {}).get("url", ""),
            }
            for fid, pre_texts in family_pre_texts.items()
            if len(pre_texts) > 1
        ],
        key=lambda x: -x["distinct_description_count"],
    )

    report = {
        "date": date_str,
        "feed_file": feed_path.name,
        "volume": {
            "total_rows": total_rows,
            "unique_parent_ids": len(parent_ids),
            "unique_ids": len(ids),
            "total_urls": len(urls),
        },
        "departments": dept_stats,
        "descriptions": {
            "unique_ids_assessed": len(seen_id_for_desc),
            "missing_count": desc_quality["missing"],
            "short_count": desc_quality["short"],
            "good_count": desc_quality["good"],
            "long_count": desc_quality["long"],
            "missing_family_ids": missing_family_ids[:50],
            "cross_parent_duplicate_count": len(cross_parent_duplicates),
            "cross_parent_duplicate_examples": cross_parent_duplicates,
            "family_description_issue_count": len(family_description_issues),
            "family_description_issues": family_description_issues[:50],
        },
        "pricing": {
            "min": round(min(prices), 2) if prices else None,
            "max": round(max(prices), 2) if prices else None,
            "mean": round(statistics.mean(prices), 2) if prices else None,
            "median": round(statistics.median(prices), 2) if prices else None,
            "no_price_count": len(no_price_ids),
            "with_sale_price_count": sale_price_count,
        },
        "availability": dict(availability_counts.most_common()),
        "occasion_products": {
            "is_occasion_count": is_occasion_count,
            "by_occasion_type": dict(occasion_counts.most_common()),
        },
        "id_quality_details": id_details,
        "family_examples": family_examples,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"report_{date_str}.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Report saved to {report_path}")
    return report


def print_report(report: dict) -> None:
    v = report["volume"]
    d = report["descriptions"]
    p = report["pricing"]

    print(f"\n{'='*60}")
    print(f"  Feed Report — {report['date']}")
    print(f"{'='*60}")

    print(f"\nVOLUME")
    print(f"  Total rows:        {v['total_rows']:>8,}")
    print(f"  Unique parent IDs: {v['unique_parent_ids']:>8,}")
    print(f"  Unique IDs:        {v['unique_ids']:>8,}")
    print(f"  Total URLs:        {v['total_urls']:>8,}")

    print(f"\nDEPARTMENTS  (top 10 by URL count)")
    print(f"  {'Department':<35} {'URLs':>6}  {'Mean £':>8}  {'Median £':>8}")
    for dept, data in list(report["departments"].items())[:10]:
        print(f"  {dept:<35} {data['url_count']:>6,}  {str(data['price_mean'] or '-'):>8}  {str(data['price_median'] or '-'):>8}")

    print(f"\nDESCRIPTIONS  (unique IDs assessed: {d['unique_ids_assessed']:,})")
    print(f"  Missing pre-content:          {d['missing_count']:>6,}")
    print(f"  Short  (<{DESC_SHORT_WORDS} words):         {d['short_count']:>6,}")
    print(f"  Good   ({DESC_SHORT_WORDS}–{DESC_LONG_WORDS} words):       {d['good_count']:>6,}")
    print(f"  Long   (>{DESC_LONG_WORDS} words):         {d['long_count']:>6,}")
    print(f"  Cross-parent duplicates:      {d['cross_parent_duplicate_count']:>6,}")
    print(f"  Families with mixed descs:    {d['family_description_issue_count']:>6,}")

    print(f"\nPRICING")
    print(f"  Min:               {p['min']:>8}")
    print(f"  Max:               {p['max']:>8}")
    print(f"  Mean:              {p['mean']:>8}")
    print(f"  Median:            {p['median']:>8}")
    print(f"  No price:          {p['no_price_count']:>8,}")
    print(f"  With sale price:   {p['with_sale_price_count']:>8,}")

    print(f"\nAVAILABILITY")
    for status, count in report["availability"].items():
        print(f"  {status:<35} {count:>6,}")

    print(f"\nOCCASION PRODUCTS")
    occ = report["occasion_products"]
    print(f"  Occasion products: {occ['is_occasion_count']:>8,}")
    for occasion, count in list(occ["by_occasion_type"].items())[:10]:
        print(f"  {occasion:<35} {count:>6,}")

    print()


if __name__ == "__main__":
    from datetime import date
    from exporter import export_text, export_excel

    feeds_dir = Path(__file__).parent / "data" / "feeds"
    today_feed = feeds_dir / f"feed_{date.today()}.csv"
    report = analyse(today_feed)
    print_report(report)
    export_text(report)
    export_excel(report)
