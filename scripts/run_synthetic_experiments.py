"""Run paired portable estimator baselines and write JSON results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uav_tracking.experiments import run_estimator_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-class", choices=["person", "car", "both"], default="both")
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--output", type=Path, default=Path("results/synthetic_estimator_baselines.json"))
    args = parser.parse_args()
    if args.seeds <= 0:
        parser.error("--seeds must be positive")
    classes = ["person", "car"] if args.target_class == "both" else [args.target_class]
    records = []
    for target_class in classes:
        records.extend(
            record.as_dict()
            for record in run_estimator_benchmark(
                target_class=target_class,
                seeds=range(args.seeds),
                steps=args.steps,
                dt=args.dt,
            )
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

