import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

URL_ALERT_THRESHOLD = 100


def _smtp_config() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from": os.environ.get("EMAIL_FROM", os.environ.get("SMTP_USER", "")),
        "to": [a.strip() for a in os.environ.get("EMAIL_TO", "").split(",") if a.strip()],
    }


def _send(subject: str, body: str) -> None:
    cfg = _smtp_config()
    if not all([cfg["host"], cfg["user"], cfg["password"], cfg["to"]]):
        print("SMTP not configured — skipping email notification.")
        return

    msg = MIMEMultipart()
    msg["From"] = cfg["from"]
    msg["To"] = ", ".join(cfg["to"])
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from"], cfg["to"], msg.as_string())
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("SMTP authentication failed — check SMTP_USER and SMTP_PASSWORD in .env") from None
    except smtplib.SMTPConnectError:
        raise RuntimeError(f"Could not connect to SMTP server at {cfg['host']}:{cfg['port']}") from None
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"SMTP error while sending '{subject}': {type(exc).__name__}") from None

    print(f"Email sent: {subject}")


def _build_body(comp: dict, label: str) -> str:
    u = comp["urls"]
    r = comp["rows"]
    ids = comp["ids"]
    nf = comp["new_family_ids"]
    rf = comp["removed_family_ids"]
    d = comp["descriptions"]
    p = comp["pricing"]

    url_alert = "  *** DRAMATIC CHANGE ***" if u["dramatic_change"] else ""

    dept_lines = "\n".join(
        f"  {dept:<40} {ch['yesterday']:>5,} -> {ch['today']:>5,}  ({ch['change']:+,})"
        for dept, ch in list(comp["department_changes"].items())[:15]
    ) or "  No department changes."

    new_family_lines = "\n".join(
        f"  {e['family_id']}: {e['title'][:60]}" + (f"\n    {e['url']}" if e.get("url") else "")
        for e in nf["examples"][:20]
    ) or "  None"

    removed_lines = "\n".join(f"  {fid}" for fid in rf["ids"][:20]) or "  None"

    return (
        f"{label}: {comp['today']} vs {comp['yesterday']}\n"
        f"{'=' * 60}\n\n"
        f"VOLUME\n"
        f"  URLs:  {u['yesterday']:,} -> {u['today']:,}  ({u['change']:+,} / {u['change_pct']:+.1f}%){url_alert}\n"
        f"  Rows:  {r['yesterday']:,} -> {r['today']:,}  ({r['change']:+,})\n\n"
        f"PRODUCT CHANGES\n"
        f"  New product IDs:      {ids['new_count']:,}\n"
        f"  Removed product IDs:  {ids['removed_count']:,}\n"
        f"  New product families: {nf['count']:,}\n"
        f"  Removed families:     {rf['count']:,}\n\n"
        f"New families (sample):\n{new_family_lines}\n\n"
        f"Removed families (sample):\n{removed_lines}\n\n"
        f"DEPARTMENT CHANGES (top 15 by absolute change)\n"
        f"  {'Department':<40} {'Yesterday':>9}   {'Today':>5}   Change\n"
        f"{dept_lines}\n\n"
        f"DESCRIPTION QUALITY\n"
        f"  Missing:               {d['missing_yesterday']:,} -> {d['missing_today']:,}  ({d['missing_change']:+,})\n"
        f"  Cross-family dups:     {d['cross_parent_duplicates_yesterday']:,} -> {d['cross_parent_duplicates_today']:,}\n"
        f"  Family inconsistencies:{d['family_issues_yesterday']:,} -> {d['family_issues_today']:,}\n\n"
        f"PRICING\n"
        f"  Mean:   £{p['mean_yesterday']} -> £{p['mean_today']}\n"
        f"  Median: £{p['median_yesterday']} -> £{p['median_today']}\n"
    )


def notify_daily(comp: dict) -> None:
    url_change = comp["urls"]["change"]
    new_family_count = comp["new_family_ids"]["count"]
    date = comp["today"]

    if url_change != 0:
        direction = "up" if url_change > 0 else "down"
        tag = "[ALERT]" if abs(url_change) >= URL_ALERT_THRESHOLD else "[UPDATE]"
        subject = f"{tag} RH Feed — URLs {direction} {abs(url_change):,} ({date})"
        _send(subject, _build_body(comp, "Daily alert"))

    if new_family_count > 0:
        subject = f"[NEW PRODUCTS] RH Feed — {new_family_count} new {'family' if new_family_count == 1 else 'families'} ({date})"
        _send(subject, _build_body(comp, "New product alert"))


def notify_weekly(comp: dict) -> None:
    subject = f"[Weekly] RH Feed — {comp['today']} vs {comp['yesterday']}"
    _send(subject, _build_body(comp, "Weekly summary"))
