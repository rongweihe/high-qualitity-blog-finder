from __future__ import annotations

import argparse

from .collectors import blogroll, forever_blog, github_blog_list
from .importer import import_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect blogger candidates from configured sources.")
    parser.add_argument(
        "--source",
        choices=["github_blog_list", "forever_blog", "blogroll", "all"],
        default="all",
        help="Source collector to run.",
    )
    parser.add_argument("--max", type=int, default=500, help="Maximum candidates to import per run.")
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=160,
        help="Maximum Forever Blog detail pages to inspect in one run.",
    )
    parser.add_argument(
        "--include-broad",
        action="store_true",
        help="Import broad Forever Blog entries even when tech relevance is not detected.",
    )
    parser.add_argument(
        "--with-blogroll",
        action="store_true",
        help="Run blogroll discovery after the selected source collectors.",
    )
    parser.add_argument(
        "--blogroll-depth",
        type=int,
        default=1,
        help="How many friend-link hops to follow.",
    )
    parser.add_argument(
        "--blogroll-workers",
        type=int,
        default=4,
        help="Subprocess worker count for blogroll discovery.",
    )
    parser.add_argument(
        "--blogroll-seed-limit",
        type=int,
        default=80,
        help="Maximum existing bloggers to use as blogroll seeds.",
    )
    parser.add_argument(
        "--blogroll-page-limit",
        type=int,
        default=4,
        help="Maximum friend-link pages to try per blogger.",
    )
    parser.add_argument(
        "--blogroll-seed-url",
        action="append",
        default=[],
        help="Specific seed site URL for blogroll discovery. Can be provided multiple times.",
    )
    args = parser.parse_args()

    total = 0
    if args.source in {"github_blog_list", "all"}:
        candidates = github_blog_list.collect(max_items=args.max)
        imported = import_candidates(candidates, max_items=args.max)
        total += imported
        print(f"github_blog_list: imported {imported} candidates")

    if args.source in {"forever_blog", "all"}:
        candidates = forever_blog.collect(
            max_items=args.max,
            include_broad=args.include_broad,
            detail_limit=args.detail_limit,
        )
        imported = import_candidates(candidates, max_items=args.max)
        total += imported
        print(f"forever_blog: imported {imported} candidates")

    if args.source == "blogroll" or args.with_blogroll:
        candidates = blogroll.collect(
            max_items=args.max,
            depth=args.blogroll_depth,
            workers=args.blogroll_workers,
            seed_limit=args.blogroll_seed_limit,
            page_limit=args.blogroll_page_limit,
            seed_urls=args.blogroll_seed_url,
        )
        imported = import_candidates(candidates, max_items=args.max)
        total += imported
        print(f"blogroll: imported {imported} candidates")

    print(f"total imported: {total}")


if __name__ == "__main__":
    main()
