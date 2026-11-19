"""Latency and cost report from the request_log table (every answer served by the API / UI).

Usage:
    uv run python eval/usage_report.py              # last 7 days
    uv run python eval/usage_report.py --days 30
    uv run python eval/usage_report.py --top 10     # also list the 10 most expensive requests
"""

import argparse

import psycopg

from finsight.config import settings

SUMMARY_SQL = """
SELECT mode,
       cached,
       count(*)                                                    AS requests,
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY seconds)       AS p50_s,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY seconds)       AS p95_s,
       max(seconds)                                                AS max_s,
       avg(llm_calls)                                              AS avg_calls,
       avg(input_tokens + output_tokens)                           AS avg_tokens,
       avg(cost_usd)                                               AS avg_cost,
       sum(cost_usd)                                               AS total_cost
FROM request_log
WHERE created_at > now() - make_interval(days => %s)
GROUP BY mode, cached
ORDER BY mode, cached
"""

TOP_SQL = """
SELECT created_at, mode, seconds, llm_calls, cost_usd, left(question, 90)
FROM request_log
WHERE created_at > now() - make_interval(days => %s)
ORDER BY cost_usd DESC NULLS LAST
LIMIT %s
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--top", type=int, default=5, help="how many of the most expensive requests to list")
    args = parser.parse_args()

    with psycopg.connect(settings.psycopg_url) as conn:
        exists = conn.execute("SELECT to_regclass('request_log')").fetchone()[0]
        if not exists:
            print("No request_log table yet: ask a question through the API or UI first.")
            return
        rows = conn.execute(SUMMARY_SQL, (args.days,)).fetchall()
        top = conn.execute(TOP_SQL, (args.days, args.top)).fetchall()

    print(f"Requests in the last {args.days} days\n")
    print(f"{'mode':<10}{'cached':<8}{'requests':>9}{'p50 s':>8}{'p95 s':>8}{'max s':>8}"
          f"{'calls':>7}{'tokens':>9}{'avg $':>10}{'total $':>10}")
    for mode, cached, n, p50, p95, mx, calls, tokens, avg_cost, total in rows:
        print(f"{mode:<10}{'yes' if cached else 'no':<8}{n:>9}{p50:>8.1f}{p95:>8.1f}{mx:>8.1f}"
              f"{float(calls or 0):>7.1f}{float(tokens or 0):>9.0f}{float(avg_cost or 0):>10.4f}{float(total or 0):>10.4f}")

    if top:
        print("\nMost expensive requests")
        for created, mode, seconds, calls, cost, q in top:
            print(f"  ${float(cost or 0):.4f}  {seconds:5.1f}s  {calls:>2} calls  {mode:<9} {created:%m-%d %H:%M}  {q}")


if __name__ == "__main__":
    main()
