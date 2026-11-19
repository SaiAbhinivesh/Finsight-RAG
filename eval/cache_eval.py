"""Choose the semantic cache threshold: which question pairs should share an answer, and which must not.

Usage:
    uv run python eval/cache_eval.py
"""

from finsight.cache.semantic_cache import entity_key, similarity

# Same question, different words: these SHOULD hit the cache
SAME = [
    ("What was 3M's capital expenditure in FY2018?",
     "How much did 3M spend on capex in fiscal 2018?"),
    ("What production rate changes is Boeing forecasting for FY2023?",
     "What production rate changes does Boeing expect in 2023?"),
    ("Did AMD report customer concentration in FY22?",
     "Does AMD depend on a few large customers in FY2022?"),
    ("What is the FY2022 unadjusted EBITDA % margin for PepsiCo?",
     "What was PepsiCo's unadjusted EBITDA margin in FY22?"),
    ("Has PepsiCo reported any material legal proceedings in FY2022?",
     "Is PepsiCo involved in any significant lawsuits according to its FY2022 10-K?"),
    ("What are the major products and services that AMD sells as of FY22?",
     "What does AMD sell as of fiscal year 2022?"),
    ("What was Verizon's net income in FY2021?",
     "How much net income did Verizon report for 2021?"),
    ("Which debt securities are registered to trade on a national securities exchange under American Express' name as of 2022?",
     "As of 2022, which American Express debt securities are listed on a national exchange?"),
]

# Look alike, different answer: these must NEVER hit the cache
DIFFERENT = [
    ("What was AMD's revenue in FY2022?",
     "What was AMD's revenue in FY2015?"),                                   # different year
    ("What was 3M's capital expenditure in FY2018?",
     "What was 3M's capital expenditure in FY2022?"),                        # different year
    ("What was Boeing's effective tax rate in FY2022?",
     "What was 3M's effective tax rate in FY2022?"),                         # different company
    ("What was Verizon's net income in FY2021?",
     "What was Verizon's operating income in FY2021?"),                      # different metric
    ("What is PepsiCo's quick ratio for FY2022?",
     "What is PepsiCo's current ratio for FY2022?"),                         # different metric
    ("What was Boeing's revenue in FY2022?",
     "What was Boeing's net loss in FY2022?"),                               # different metric
    ("What are AMD's main risk factors in FY2022?",
     "What are AMD's main products in FY2022?"),                             # different topic
    ("How did PepsiCo's revenue change from 2021 to 2022?",
     "What was PepsiCo's revenue in 2022?"),                                 # change vs value
    ("Did AMD report customer concentration in FY22?",
     "Did AMD report supplier concentration in FY22?"),                      # different topic
]

THRESHOLDS = [0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98]


def score(pairs):
    rows = []
    for a, b in pairs:
        rows.append({"a": a, "b": b, "sim": similarity(a, b), "entities": entity_key(a) == entity_key(b)})
    return rows


def show(title, rows):
    print(f"\n{title}")
    print(f"  {'similarity':>10}  {'entities':<9} question pair")
    for r in rows:
        print(f"  {r['sim']:>10.3f}  {'match' if r['entities'] else 'DIFFER':<9} {r['a']}")
        print(f"  {'':>10}  {'':<9} {r['b']}")


def main() -> None:
    same, different = score(SAME), score(DIFFERENT)
    show("SHOULD HIT (same question, different words)", same)
    show("MUST NOT HIT (look alike, different answer)", different)

    print("\nThreshold sweep (a hit = entities match AND similarity >= threshold)")
    print(f"  {'threshold':>9}  {'correct hits':>12}  {'false hits':>10}  {'false hits w/o entity check':>27}")
    for t in THRESHOLDS:
        hits = sum(r["entities"] and r["sim"] >= t for r in same)
        false = sum(r["entities"] and r["sim"] >= t for r in different)
        false_no_guard = sum(r["sim"] >= t for r in different)
        print(f"  {t:>9.2f}  {hits:>8}/{len(same):<3}  {false:>10}  {false_no_guard:>27}")

    safe = [t for t in THRESHOLDS
            if sum(r["entities"] and r["sim"] >= t for r in different) == 0]
    if safe:
        best = min(safe)
        hits = sum(r["entities"] and r["sim"] >= best for r in same)
        print(f"\nLowest threshold with zero false hits: {best:.2f} ({hits}/{len(same)} correct hits)")
        print("Set SIMILARITY_THRESHOLD in src/finsight/cache/semantic_cache.py to this value.")
    else:
        print("\nEvery threshold gives a false hit: the entity check alone is not enough for these pairs.")


if __name__ == "__main__":
    main()
