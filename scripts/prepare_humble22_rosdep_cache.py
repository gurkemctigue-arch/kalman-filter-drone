"""Download unchanged official rosdep metadata through the Windows HTTPS stack.

This is a transport fallback for WSL networks that reset GitHub connections.
No proxy values or credentials are inspected or printed. The original files,
URLs and SHA256 hashes are retained; only the derived sources list uses file://.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("D:/WSL/UAVHumble22-validation/official-rosdep"))
    parser.add_argument("--linux-root", default="/mnt/d/WSL/UAVHumble22-validation/official-rosdep")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    base = "https://raw.githubusercontent.com/ros/rosdistro/master/"
    items = {
        "20-default.list": base + "rosdep/sources.list.d/20-default.list",
        "base.yaml": base + "rosdep/base.yaml",
        "python.yaml": base + "rosdep/python.yaml",
        "ruby.yaml": base + "rosdep/ruby.yaml",
        "osx-homebrew.yaml": base + "rosdep/osx-homebrew.yaml",
        "fuerte.yaml": base + "releases/fuerte.yaml",
        "index-v4.yaml": base + "index-v4.yaml",
        "humble/distribution.yaml": base + "humble/distribution.yaml",
    }
    records = []
    for name, url in items.items():
        # urllib uses the normal Windows trust/proxy stack; TLS verification is
        # mandatory. Network failures stop preparation instead of weakening it.
        with urllib.request.urlopen(url, timeout=45) as response:
            data = response.read()
        destination = args.output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        record = {"file": name, "official_url": url, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        records.append(record)
        print(json.dumps(record))
    sources = (args.output / "20-default.list").read_text(encoding="utf-8")
    for name, url in items.items():
        sources = sources.replace(url, "file://" + args.linux_root.rstrip("/") + "/" + name)
    # rosdep's legacy gbpdistro loader contacts more remote Fuerte metadata even
    # when the input YAML is local. It is ROS 1 data, unrelated to Humble.
    sources = "\n".join("# Humble-only cache skips legacy ROS 1 Fuerte: " + line
                        if line.startswith("gbpdistro ") else line
                        for line in sources.splitlines()) + "\n"
    (args.output / "local-sources.list").write_text(sources, encoding="utf-8")
    manifest = {"downloaded_at_utc": datetime.now(timezone.utc).isoformat(), "files": records,
                "original_yaml_unchanged": True, "derived_list": "local-sources.list",
                "legacy_ros1_fuerte_source_inactive": True}
    (args.output / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
