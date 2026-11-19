"""Convert each 10-K PDF with Docling once and cache it as JSON in data/parsed/.

Usage:
    uv run python scripts/parse_docling.py                    # all filings (skips cached)
    uv run python scripts/parse_docling.py --only AMD_2022_10K
"""

import argparse
import time

from finsight.ingestion.docling_loader import PARSED_DIR, build_converter
from finsight.ingestion.loaders import RAW_DIR, load_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="convert a single doc_name")
    args = parser.parse_args()

    rows = [r for r in load_manifest() if not args.only or r["doc_name"] == args.only]
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    converter = build_converter()

    for row in rows:
        out = PARSED_DIR / f"{row['doc_name']}.json"
        if out.exists():
            print(f"skip      {row['doc_name']}")
            continue
        start = time.perf_counter()
        result = converter.convert(str(RAW_DIR / f"{row['doc_name']}.pdf"))
        result.document.save_as_json(out)
        elapsed = time.perf_counter() - start
        pages = len(result.document.pages)
        print(f"converted {row['doc_name']:<28} {pages:>4} pages  {elapsed:6.0f}s  ({elapsed / pages:.2f}s/page)")


if __name__ == "__main__":
    main()