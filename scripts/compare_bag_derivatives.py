"""Compare two retained diagnostic derivatives; never modifies either input."""

import argparse
import hashlib
import json
from pathlib import Path


def compare(first: Path, second: Path) -> dict:
    lengths = [first.stat().st_size, second.stat().st_size]
    shorter, longer = (first, second) if lengths[0] <= lengths[1] else (second, first)
    checked, digest, first_difference = 0, hashlib.sha256(), None
    with shorter.open("rb") as left, longer.open("rb") as right:
        for block in iter(lambda: left.read(4 * 1024**2), b""):
            other = right.read(len(block))
            if block != other:
                first_difference = checked + next(i for i, pair in enumerate(zip(block, other)) if pair[0] != pair[1])
                break
            digest.update(block)
            checked += len(block)
    return {"first": str(first), "second": str(second), "input_lengths": lengths,
            "shorter": str(shorter), "longer": str(longer), "compared_equal_bytes": checked,
            "first_difference": first_difference,
            "shorter_is_exact_prefix": first_difference is None and checked == shorter.stat().st_size,
            "equal_prefix_sha256": digest.hexdigest(),
            "longer_extra_bytes": longer.stat().st_size - shorter.stat().st_size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.first.resolve(strict=True), args.second.resolve(strict=True))
    # Exclusively create an external evidence report; refuse overwrites.
    with args.report.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps(report))
