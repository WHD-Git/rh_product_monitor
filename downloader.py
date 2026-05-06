import os
import csv
import requests
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

FEED_URL = os.environ["prod_feed_source"]
DATA_DIR = Path(__file__).parent / "data" / "feeds"


def download_feed() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / f"feed_{date.today()}.csv"

    response = requests.get(FEED_URL, timeout=60)
    response.raise_for_status()

    dest.write_bytes(response.content)
    print(f"Downloaded feed to {dest}  ({len(response.content):,} bytes)")
    return dest


DELIMITER = "\t"


def open_feed(feed_path: Path):
    return feed_path.open(newline="", encoding="utf-8-sig")


def print_headers(feed_path: Path) -> None:
    with open_feed(feed_path) as f:
        reader = csv.reader(f, delimiter=DELIMITER)
        headers = next(reader)

    print(f"\nHeaders ({len(headers)} columns):")
    for i, col in enumerate(headers):
        print(f"  [{i:>3}]  {col}")


if __name__ == "__main__":
    path = download_feed()
    print_headers(path)
