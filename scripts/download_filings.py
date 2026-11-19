"""Download the 10-K PDFs listed in data/manifest.csv (or FINSIGHT_MANIFEST) into data/raw/.

Run from the project root:
    uv run python scripts/download_filings.py
Safe to re-run: files that already exist are skipped.
"""

import csv
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MANIFEST = ROOT / os.environ.get("FINSIGHT_MANIFEST", "data/manifest.csv")   # quick tour: data/manifest_quicktour.csv
RAW_DIR = ROOT / "data" / "raw"

# FinanceBench stores PDFs at /pdfs/<doc_name>.pdf in its GitHub repo
BASE_URL = "https://raw.githubusercontent.com/patronus-ai/financebench/main/pdfs/{doc_name}.pdf"


def is_real_pdf(path: Path) -> bool:
    """Every PDF starts with the bytes %PDF. Catches HTML error pages or LFS pointers."""
    with path.open("rb") as f:
        return f.read(4) == b"%PDF"


def download(doc_name: str, dest: Path) -> None:
    url = BASE_URL.format(doc_name=doc_name)
    tmp = dest.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    if not is_real_pdf(tmp):
        tmp.unlink()
        raise ValueError(f"{url} did not return a PDF")
    tmp.rename(dest)   # only a complete, valid file gets the real name


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with MANIFEST.open() as f:
        rows = list(csv.DictReader(f))

    downloaded, skipped, failed = 0, 0, []
    for row in rows:
        doc_name = row["doc_name"]
        dest = RAW_DIR / f"{doc_name}.pdf"

        if dest.exists() and is_real_pdf(dest):
            print(f"skip      {doc_name}")
            skipped += 1
            continue

        try:
            print(f"download  {doc_name} ...", end=" ", flush=True)
            download(doc_name, dest)
            size_mb = dest.stat().st_size / 1_000_000
            print(f"{size_mb:.1f} MB")
            downloaded += 1
        except Exception as e:
            print(f"FAILED ({e})")
            failed.append(doc_name)

    print(f"\nDone: {downloaded} downloaded, {skipped} skipped, {len(failed)} failed")
    if failed:
        print("Failed:", failed)


if __name__ == "__main__":
    main()