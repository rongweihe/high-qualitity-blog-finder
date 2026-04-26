from __future__ import annotations

import argparse
from datetime import date, timedelta

from .verifier.recency import verify_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify site health and recent blog updates.")
    parser.add_argument("--limit", type=int, default=500, help="Maximum bloggers to verify.")
    parser.add_argument(
        "--recent-since",
        default=(date.today() - timedelta(days=365)).isoformat(),
        help="Recent post cutoff date in YYYY-MM-DD format.",
    )
    args = parser.parse_args()
    recent_since = date.fromisoformat(args.recent_since)
    count = verify_all(limit=args.limit, recent_since=recent_since)
    print(f"verified {count} bloggers with recent_since={recent_since.isoformat()}")


if __name__ == "__main__":
    main()
