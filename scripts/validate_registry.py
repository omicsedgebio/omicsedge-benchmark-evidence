#!/usr/bin/env python3
"""Validate a Project 003 registry bundle JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark_evidence import RegistryValidationError, validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        validate_bundle(json.loads(args.bundle.read_text()))
    except (OSError, json.JSONDecodeError, RegistryValidationError) as error:
        print(f"FAIL: {error}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

