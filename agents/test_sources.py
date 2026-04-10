#!/usr/bin/env python3
"""Local test harness for research sources. Enables parameter tuning before deployment.

Usage:
    python agents/test_sources.py                          # run all sources
    python agents/test_sources.py --source github_search   # single source
    python agents/test_sources.py --since 2026-03-01       # historical window
    python agents/test_sources.py --score-threshold 0.3    # tune quality cutoff
    python agents/test_sources.py --find JuliusBrussee/caveman  # check a specific repo
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sources import ALL_SOURCES, github_search_tools

# Repos to explicitly check for in github_search results (validation targets)
VALIDATION_TARGETS = [
    "JuliusBrussee/caveman",
    "drona23/claude-token-efficient",
]


def run_source(name: str, fetcher, since_days: int, score_threshold: float) -> list[dict]:
    if name == "github_search":
        return github_search_tools(since_days=since_days, score_threshold=score_threshold)
    return fetcher()


def print_source_results(name: str, items: list[dict], find: str | None) -> None:
    print(f"\n{'=' * 60}")
    print(f"SOURCE: {name}  ({len(items)} items)")
    print("=" * 60)
    for item in items[:10]:
        title = item.get("title", "")
        url = item.get("url", "")
        text = item.get("text", "")[:120]
        marker = " *** MATCH ***" if find and find.lower() in (title + url).lower() else ""
        print(f"  {title}{marker}")
        print(f"    {url}")
        if text:
            print(f"    {text}")


def check_validation_targets(all_results: dict[str, list[dict]]) -> None:
    print(f"\n{'=' * 60}")
    print("VALIDATION TARGETS")
    print("=" * 60)
    for target in VALIDATION_TARGETS:
        found_in = []
        for source_name, items in all_results.items():
            for item in items:
                if target.lower() in (item.get("title", "") + item.get("url", "")).lower():
                    found_in.append(source_name)
                    break
        status = "FOUND in: " + ", ".join(found_in) if found_in else "NOT FOUND"
        print(f"  {target}: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test research sources locally")
    parser.add_argument(
        "--since", metavar="YYYY-MM-DD",
        help="Recency window start date (default: 30 days ago)",
    )
    parser.add_argument(
        "--source",
        help=f"Run a single source. Options: {', '.join(list(ALL_SOURCES) + ['github_search'])}",
    )
    parser.add_argument(
        "--score-threshold", type=float, default=0.4, metavar="N",
        help="Quality score cutoff for github_search (0.0–1.0, default: 0.4)",
    )
    parser.add_argument(
        "--find", metavar="TERM",
        help="Highlight results containing this term (e.g. JuliusBrussee/caveman)",
    )
    args = parser.parse_args()

    if args.since:
        since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        since_days = max((datetime.now(timezone.utc) - since_dt).days, 1)
    else:
        since_days = 30

    print(f"Settings: since_days={since_days}, score_threshold={args.score_threshold}")

    sources_to_run: dict = {}
    if args.source:
        if args.source == "github_search":
            sources_to_run = {"github_search": None}
        elif args.source in ALL_SOURCES:
            sources_to_run = {args.source: ALL_SOURCES[args.source]}
        else:
            valid = ", ".join(list(ALL_SOURCES) + ["github_search"])
            print(f"Unknown source '{args.source}'. Valid: {valid}", file=sys.stderr)
            sys.exit(1)
    else:
        sources_to_run = dict(ALL_SOURCES)
        sources_to_run["github_search"] = None

    all_results: dict[str, list[dict]] = {}
    for name, fetcher in sources_to_run.items():
        try:
            items = run_source(name, fetcher, since_days, args.score_threshold)
            all_results[name] = items
            print_source_results(name, items, args.find)
        except Exception as e:
            print(f"\nERROR in {name}: {e}", file=sys.stderr)
            all_results[name] = []

    if not args.source:
        check_validation_targets(all_results)

    print(f"\n{'=' * 60}")
    total = sum(len(v) for v in all_results.values())
    print(f"TOTAL: {total} items across {len(all_results)} sources")


if __name__ == "__main__":
    main()
