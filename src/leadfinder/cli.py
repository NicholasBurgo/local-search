"""Command-line interface for leadfinder.

Subcommands: scrape, verify, dashboard. Flags override settings in memory only;
unlike the old CLI, nothing here writes back to the .env file.
"""

from __future__ import annotations

import argparse
import sys

from .logging_setup import get_logger, setup_logging
from .models import FieldProfile


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cities", nargs="+", help='Cities, e.g. --cities "Austin TX" "Denver CO"')
    parser.add_argument("--categories", nargs="+", help="Category keys to search (default: all)")
    parser.add_argument(
        "--output-dir", default=None, help="Output directory (default: leads_output)"
    )
    parser.add_argument("--api-key", default=None, help="Google Places API key (overrides env)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leadfinder",
        description="Find local businesses without websites (Places API New).",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scrape_p = sub.add_parser("scrape", help="Collect no-website leads from the configured source")
    _add_common(scrape_p)
    scrape_p.add_argument(
        "--source",
        default=None,
        choices=["overture", "google", "both"],
        help="Data source (default: overture - free open data, no key required)",
    )
    scrape_p.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Overture: drop places below this existence confidence, 0-1 (default: 0.5)",
    )
    scrape_p.add_argument(
        "--bbox",
        default=None,
        help="Manual bounding box 'west,south,east,north' (skips geocoding)",
    )
    scrape_p.add_argument(
        "--profile",
        default=None,
        choices=[p.value for p in FieldProfile],
        help="Field profile controlling data richness and cost (default: enterprise)",
    )
    scrape_p.add_argument("--max-results", type=int, default=None, help="Results per query (1-20)")
    scrape_p.add_argument(
        "--monthly-budget", type=int, default=None, help="Soft monthly call budget"
    )
    scrape_p.add_argument(
        "--request-delay", type=float, default=None, help="Delay between calls (s)"
    )

    verify_p = sub.add_parser("verify", help="Probe candidate domains to confirm no-website leads")
    _add_common(verify_p)
    verify_p.add_argument("--probe-concurrency", type=int, default=None, help="Concurrent probes")
    verify_p.add_argument("--probe-timeout", type=float, default=None, help="Per-probe timeout (s)")

    dash_p = sub.add_parser("dashboard", help="Build an HTML dashboard from the latest CSV")
    dash_p.add_argument("--output-dir", default=None, help="Where to find leads CSVs")
    dash_p.add_argument("--output-file", default=None, help="Dashboard HTML path")

    return parser


def _settings_overrides(args: argparse.Namespace) -> dict:
    mapping = {
        "cities": getattr(args, "cities", None),
        "categories": getattr(args, "categories", None),
        "output_dir": getattr(args, "output_dir", None),
        "api_key": getattr(args, "api_key", None),
        "source": getattr(args, "source", None),
        "min_confidence": getattr(args, "min_confidence", None),
        "bbox": getattr(args, "bbox", None),
        "field_profile": getattr(args, "profile", None),
        "max_results": getattr(args, "max_results", None),
        "monthly_call_budget": getattr(args, "monthly_budget", None),
        "request_delay": getattr(args, "request_delay", None),
        "probe_concurrency": getattr(args, "probe_concurrency", None),
        "probe_timeout": getattr(args, "probe_timeout", None),
        "log_level": getattr(args, "log_level", None),
    }
    return {k: v for k, v in mapping.items() if v is not None}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.log_level or "INFO")
    logger = get_logger()

    try:
        if args.command == "scrape":
            from .scrape import main as run_scrape

            run_scrape(**_settings_overrides(args))
        elif args.command == "verify":
            from .verify import main as run_verify

            run_verify(**_settings_overrides(args))
        elif args.command == "dashboard":
            from .analytics import main as run_dashboard

            run_dashboard(
                output_dir=args.output_dir or "leads_output",
                output_file=args.output_file,
            )
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        return 130
    except Exception as exc:
        logger.error("Command failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
