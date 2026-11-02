"""Read-only CLI for the pinned Humble DDS runtime contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from uav_tracking.dds_runtime import environment, preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["environment", "verify"])
    parser.add_argument("--registration", required=True)
    parser.add_argument("--current-library-path", default=None)
    args = parser.parse_args()
    try:
        if args.action == "environment":
            print(environment(args.registration, current_library_path=args.current_library_path))
        else:
            print(json.dumps(preflight(args.registration), indent=2))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"DDS runtime verification failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
