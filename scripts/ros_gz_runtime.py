#!/usr/bin/env python3
"""Register or verify an explicit ros_gz overlay; starts no ROS or simulation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from uav_tracking.ros_gz_runtime import (  # noqa: E402
    RuntimeRegistrationError, create_registration, verify_live_process, verify_registration,
)


def publish(path, value):
    path = Path(path)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    register = commands.add_parser("register", help="Create a candidate requiring independent review")
    register.add_argument("--overlay-root", type=Path, required=True)
    register.add_argument("--repo-root", type=Path, required=True)
    register.add_argument("--patch", type=Path)
    register.add_argument("--plugin-elf", type=Path, action="append", default=[],
                          help="Explicit dynamically loaded ELF and its ldd closure; repeat for each plugin")
    register.add_argument("--expected-commit")
    register.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="Compare current files and optional live bridge PID")
    verify.add_argument("--registration", type=Path, required=True)
    verify.add_argument("--expected-registration-sha256", help="SHA from the independent review, checked before parsing")
    verify.add_argument("--patch", type=Path, help="Frozen copy of the same registered patch; bytes/SHA must match")
    verify.add_argument("--pid", type=int)
    verify.add_argument("--pid-start-ticks", type=int)
    verify.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "register":
            if args.output.exists():
                raise RuntimeRegistrationError("Refusing to overwrite existing registration")
            value = create_registration(args.overlay_root, args.repo_root, patch_path=args.patch,
                                        expected_commit=args.expected_commit, plugin_elf_paths=args.plugin_elf)
            publish(args.output, value)
            print(json.dumps({"status": "CANDIDATE_WRITTEN_REQUIRES_REVIEW", "output": str(args.output),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "registration_digest": value["registration_digest"]}))
        else:
            if args.pid_start_ticks is not None and args.pid is None:
                raise RuntimeRegistrationError("--pid-start-ticks requires --pid")
            data = args.registration.read_bytes()
            if len(data) > 8 * 1024 * 1024:
                raise RuntimeRegistrationError("Registration exceeded size bound")
            digest = hashlib.sha256(data).hexdigest()
            if args.expected_registration_sha256 and digest != args.expected_registration_sha256:
                raise RuntimeRegistrationError("Registration file differs from independently reviewed SHA")
            value = json.loads(data.decode("utf-8-sig"))
            result = (verify_live_process(value, args.pid, expected_start_ticks=args.pid_start_ticks, patch_path=args.patch)
                      if args.pid is not None else verify_registration(value, patch_path=args.patch))
            result["registration_file_sha256"] = digest
            if args.output:
                publish(args.output, result)
            print(json.dumps(result, ensure_ascii=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
