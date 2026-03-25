#!/usr/bin/env python3
"""CLI tool for generating CutPilot activation codes (admin use only).

Usage:
    python tools/generate_license.py --machine-id <id> --expiry 2026-06-30
    python tools/generate_license.py --machine-id <id> --months 3
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

# Allow running from project root
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from core.license import generate_activation_code, get_machine_id


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate CutPilot activation codes.",
    )
    parser.add_argument(
        "--machine-id",
        required=True,
        help="Target machine ID (from get_machine_id())",
    )

    expiry_group = parser.add_mutually_exclusive_group(required=True)
    expiry_group.add_argument(
        "--expiry",
        type=str,
        help="Expiration date in YYYY-MM-DD format",
    )
    expiry_group.add_argument(
        "--months",
        type=int,
        help="Number of months from today",
    )

    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.expiry:
        try:
            expiry = date.fromisoformat(args.expiry)
        except ValueError:
            print(f"Error: Invalid date format '{args.expiry}', use YYYY-MM-DD")
            sys.exit(1)
    else:
        expiry = date.today() + timedelta(days=args.months * 30)

    if expiry <= date.today():
        print(f"Warning: expiry date {expiry.isoformat()} is in the past!")

    code = generate_activation_code(args.machine_id, expiry)

    print(f"Machine ID : {args.machine_id}")
    print(f"Expiry     : {expiry.isoformat()}")
    print(f"Code       : {code}")


if __name__ == "__main__":
    main()
