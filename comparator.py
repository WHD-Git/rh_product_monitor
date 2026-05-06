import csv
import json
from pathlib import Path
from datetime import date, timedelta

from downloader import DELIMITER, open_feed

REPORTS_DIR = Path(__file__).parent / "data" / "reports"
FEEDS_DIR = Path(__file__).parent / "data" / "feeds"

URL_CHANGE_THRESHOLD_PCT = 5.0


def _load_ids_from_feed(feed_path: Path) -> tuple[set[str], set[str]]:
    """Return (family_ids, product_ids) with "-" parent_id normalised to the product id."""
    family_ids: set[str] = set()
    ids: set[str] = set()
    with open_feed(feed_path) as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        for row in reader:
            pid = row.get("parent_id", "").strip()
            rid = row.get("id", "").strip()
            effective_pid = rid if pid == "-" or not pid else pid
            family_ids.add(effective_pid)
            if rid:
                ids.add(rid)
    return family_ids, ids


def compare(today_report: dict, yesterday_report: dict, today_feed: Path, yesterday_feed: Path) -> dict:
    tv = today_report["volume"]
    yv = yesterday_report["volume"]

    url_change = tv["total_urls"] - yv["total_urls"]
    url_change_pct = (url_change / yv["total_urls"] * 100) if yv["total_urls"] else 0
    url_dramatic = abs(url_change_pct) >= URL_CHANGE_THRESHOLD_PCT

    today_family_ids, today_ids = _load_ids_from_feed(today_feed)
    yesterday_family_ids, yesterday_ids = _load_ids_from_feed(yesterday_feed)

    new_ids = sorted(today_ids - yesterday_ids)
    removed_ids = sorted(yesterday_ids - today_ids)

    new_family_id_set = sorted(today_family_ids - yesterday_family_ids)
    removed_family_id_set = sorted(yesterday_family_ids - today_family_ids)

    # Attach example title + URL for each new family_id from today's report
    today_examples = today_report.get("family_examples", {})
    new_family_examples = [
        {
            "family_id": fid,
            "title": today_examples.get(fid, {}).get("title", ""),
            "url": today_examples.get(fid, {}).get("url", ""),
        }
        for fid in new_family_id_set
    ]

    # Department URL count comparison (departments now a dict of dicts)
    today_depts = today_report["departments"]
    yesterday_depts = yesterday_report["departments"]
    all_depts = set(today_depts) | set(yesterday_depts)
    dept_changes = {}
    for dept in all_depts:
        t = today_depts.get(dept, {}).get("url_count", 0)
        y = yesterday_depts.get(dept, {}).get("url_count", 0)
        if t != y:
            dept_changes[dept] = {"yesterday": y, "today": t, "change": t - y}

    comparison = {
        "today": today_report["date"],
        "yesterday": yesterday_report["date"],
        "urls": {
            "yesterday": yv["total_urls"],
            "today": tv["total_urls"],
            "change": url_change,
            "change_pct": round(url_change_pct, 2),
            "dramatic_change": url_dramatic,
        },
        "rows": {
            "yesterday": yv["total_rows"],
            "today": tv["total_rows"],
            "change": tv["total_rows"] - yv["total_rows"],
        },
        "ids": {
            "new_count": len(new_ids),
            "removed_count": len(removed_ids),
            "new": new_ids[:100],
            "removed": removed_ids[:100],
        },
        "new_family_ids": {
            "count": len(new_family_id_set),
            "examples": new_family_examples,
        },
        "removed_family_ids": {
            "count": len(removed_family_id_set),
            "ids": removed_family_id_set[:100],
        },
        "department_changes": dict(
            sorted(dept_changes.items(), key=lambda x: abs(x[1]["change"]), reverse=True)
        ),
        "descriptions": {
            "missing_yesterday": yesterday_report["descriptions"]["missing_count"],
            "missing_today": today_report["descriptions"]["missing_count"],
            "missing_change": (
                today_report["descriptions"]["missing_count"]
                - yesterday_report["descriptions"]["missing_count"]
            ),
            "cross_parent_duplicates_yesterday": yesterday_report["descriptions"]["cross_parent_duplicate_count"],
            "cross_parent_duplicates_today": today_report["descriptions"]["cross_parent_duplicate_count"],
            "family_issues_yesterday": yesterday_report["descriptions"]["family_description_issue_count"],
            "family_issues_today": today_report["descriptions"]["family_description_issue_count"],
        },
        "pricing": {
            "mean_yesterday": yesterday_report["pricing"]["mean"],
            "mean_today": today_report["pricing"]["mean"],
            "median_yesterday": yesterday_report["pricing"]["median"],
            "median_today": today_report["pricing"]["median"],
        },
    }

    report_path = REPORTS_DIR / f"comparison_{today_report['date']}_vs_{yesterday_report['date']}.json"
    report_path.write_text(json.dumps(comparison, indent=2))
    print(f"Comparison saved to {report_path}")
    return comparison


def print_comparison(comp: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  Comparison: {comp['today']} vs {comp['yesterday']}")
    print(f"{'='*60}")

    u = comp["urls"]
    flag = "  *** DRAMATIC CHANGE ***" if u["dramatic_change"] else ""
    print(f"\nURLs")
    print(f"  Yesterday: {u['yesterday']:>8,}")
    print(f"  Today:     {u['today']:>8,}  ({u['change']:+,} / {u['change_pct']:+.1f}%){flag}")

    r = comp["rows"]
    print(f"\nRows")
    print(f"  Yesterday: {r['yesterday']:>8,}")
    print(f"  Today:     {r['today']:>8,}  ({r['change']:+,})")

    ids = comp["ids"]
    print(f"\nProduct IDs")
    print(f"  New:       {ids['new_count']:>8,}")
    print(f"  Removed:   {ids['removed_count']:>8,}")

    nf = comp["new_family_ids"]
    print(f"\nNew Family IDs: {nf['count']:,}")
    for entry in nf["examples"][:20]:
        print(f"  {entry['family_id']}")
        if entry["title"]:
            print(f"    Title: {entry['title'][:80]}")
        if entry["url"]:
            print(f"    URL:   {entry['url']}")

    rf = comp["removed_family_ids"]
    print(f"\nRemoved Family IDs: {rf['count']:,}")
    for fid in rf["ids"][:20]:
        print(f"  {fid}")

    if comp["department_changes"]:
        print(f"\nDEPARTMENT CHANGES (URL count)")
        for dept, ch in list(comp["department_changes"].items())[:10]:
            print(f"  {dept:<35} {ch['yesterday']:>5,} -> {ch['today']:>5,}  ({ch['change']:+,})")

    d = comp["descriptions"]
    print(f"\nDESCRIPTIONS")
    print(f"  Missing: {d['missing_yesterday']:,} -> {d['missing_today']:,}  ({d['missing_change']:+,})")
    print(f"  Cross-family duplicates: {d['cross_parent_duplicates_yesterday']:,} -> {d['cross_parent_duplicates_today']:,}")
    print(f"  Family inconsistencies:  {d['family_issues_yesterday']:,} -> {d['family_issues_today']:,}")

    p = comp["pricing"]
    print(f"\nPRICING")
    print(f"  Mean:   £{p['mean_yesterday']} -> £{p['mean_today']}")
    print(f"  Median: £{p['median_yesterday']} -> £{p['median_today']}")
    print()


if __name__ == "__main__":
    from exporter import export_excel, export_comparison_text
    from notifier import notify_daily, notify_weekly

    today = date.today()
    today_str = str(today)
    yesterday_str = str(today - timedelta(days=1))

    today_feed = FEEDS_DIR / f"feed_{today_str}.csv"
    yesterday_feed = FEEDS_DIR / f"feed_{yesterday_str}.csv"
    today_report_path = REPORTS_DIR / f"report_{today_str}.json"
    yesterday_report_path = REPORTS_DIR / f"report_{yesterday_str}.json"

    if not yesterday_feed.exists():
        print(f"No previous feed found ({yesterday_feed.name}) — skipping comparison.")
    else:
        today_report = json.loads(today_report_path.read_text())
        yesterday_report = json.loads(yesterday_report_path.read_text())
        comp = compare(today_report, yesterday_report, today_feed, yesterday_feed)
        print_comparison(comp)
        export_excel(today_report, comp)
        export_comparison_text(comp)
        notify_daily(comp)

    # Monday: also run week-on-week comparison and send weekly summary
    if today.weekday() == 0:
        last_monday_str = str(today - timedelta(days=7))
        last_monday_feed = FEEDS_DIR / f"feed_{last_monday_str}.csv"
        last_monday_report_path = REPORTS_DIR / f"report_{last_monday_str}.json"

        if not last_monday_feed.exists():
            print(f"No feed found for last Monday ({last_monday_str}) — skipping weekly comparison.")
        else:
            print(f"\nRunning week-on-week comparison ({today_str} vs {last_monday_str})...")
            today_report = json.loads(today_report_path.read_text())
            last_monday_report = json.loads(last_monday_report_path.read_text())
            weekly_comp = compare(today_report, last_monday_report, today_feed, last_monday_feed)
            print_comparison(weekly_comp)
            export_comparison_text(weekly_comp)
            notify_weekly(weekly_comp)
