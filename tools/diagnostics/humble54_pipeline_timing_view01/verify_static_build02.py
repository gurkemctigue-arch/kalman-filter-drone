"""Verify the six copied summaries and preserve prior browser evidence hashes."""
from pathlib import Path
from datetime import datetime, timezone
import ast
import hashlib
import json
import math
import re
import statistics

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/diagnostics/humble54_pipeline_timing_view01"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    source = Path(__file__).with_name("build_view.py")
    ast.parse(source.read_text(encoding="utf8"))
    html = (OUT / "index.html").read_text(encoding="utf8")
    manifest = json.loads((OUT / "build_manifest.json").read_text(encoding="utf8"))
    payload = json.loads(re.search(r'<script type="application/json" id="dataset">(.*?)</script>', html, re.S).group(1))
    runs = payload["runs"]
    checks, stats_rows = [], []

    def check(name, condition):
        checks.append({"name": name, "pass": bool(condition)})
        if not condition:
            raise AssertionError(name)

    check("six_exact_closed_summaries", {row["id"] for row in runs} == {
        "humble54_pipeline_timing_" + name for name in ("run01", "run02", "run03", "run04", "full_person01", "full_car01")})
    check("source_sha_unchanged", digest(source.read_bytes()) == manifest["source"]["sha256"]
          == "79a3e839121275bd0acea3a2e65ebfc5e32f4d51d11bd53a7a610626c631e30d")
    check("output_sha_matches", digest((OUT / "index.html").read_bytes()) == manifest["output"]["sha256"])
    check("all_85_build_checks_pass", sum(len(row["checks"]) for row in manifest["checks"]) == 85
          and all(item["pass"] for row in manifest["checks"] for item in row["checks"]))
    check("formal_and_physical_limits_preserved", manifest["formal_progress"] == "0/280_UNCHANGED"
          and manifest["physical_e2e"] == "NOT_OBSERVED" and "正式验收：0 / 280" in html and "1857/1857 UNKNOWN" in html)
    for item, view in zip(manifest["inputs"], runs):
        raw = (ROOT / item["path"]).read_bytes()
        data = json.loads(raw)
        label = view["label"]
        check(label + "_input_sha_bytes", digest(raw) == item["sha256"] == view["sha256"]
              and len(raw) == item["bytes"] == view["bytes"])
        if label in ("run01", "run02"):
            check(label + "_missing_not_zero", view["adapter_callback_count"] is None and view["received_rgb_count"] is None
                  and view["statistics_ns"]["n"] is None and view["first_statistics_ns"]["n"] is None
                  and view["status"] == "NOT_OBSERVED_INCOMPLETE_EXECUTION")
            continue
        commands, rgb = data["commands"], data["rgb_opportunities"]
        values = sorted(row["latency_ns"] for row in commands if row["status"] == "CANDIDATE_SOFTWARE_LATENCY")
        first = sorted(row["first_candidate_latency_ns"] for row in rgb
                       if type(row.get("first_candidate_latency_ns")) in (int, float)
                       and math.isfinite(row["first_candidate_latency_ns"]) and row["first_candidate_latency_ns"] >= 0)
        check(label + "_complete_independent_denominators", len(commands) == view["adapter_callback_count"]
              and len(rgb) == view["received_rgb_count"] and len(values) == view["candidate_command_count"]
              and sum(row["outcome"] == "CANDIDATE" for row in rgb) == view["rgb_with_candidate_count"])
        for kind, population in (("all_commands", values), ("first_per_rgb", first)):
            expected = {"n": len(population), "median": statistics.median(population) if population else None,
                        "p95": population[int((len(population) - 1) * .95 + .5)] if population else None,
                        "max": max(population, default=None)}
            actual = view["statistics_ns" if kind == "all_commands" else "first_statistics_ns"]
            check(label + "_" + kind + "_statistics", actual == expected)
        stats_rows.append({"run": label, "status": view["status"],
                           "adapter_callback_count": view["adapter_callback_count"], "candidate_command_count": view["candidate_command_count"],
                           "received_rgb_count": view["received_rgb_count"], "rgb_with_candidate_count": view["rgb_with_candidate_count"],
                           "command_statistics_ns": view["statistics_ns"], "first_rgb_statistics_ns": view["first_statistics_ns"],
                           "categories": view["categories"]})
    old = json.loads((OUT / "build_archive01/preservation_manifest01.json").read_text(encoding="utf8"))
    for row in old:
        target = OUT / row["preserved"] if "preserved" in row else ROOT / row["archive"]
        check("preserve_" + target.name, digest(target.read_bytes()) == row["sha256"])
    report = {"verified_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "WINDOWS_STATIC_COPIED_CLOSED_SUMMARIES_ONLY_NO_BROWSER_NO_NATIVE", "source": manifest["source"],
              "output": manifest["output"], "input_count": len(manifest["inputs"]),
              "input_bytes": sum(row["bytes"] for row in manifest["inputs"]), "build_count_checks": 85,
              "static_checks": checks, "runs": stats_rows,
              "previous_browser_evidence": "PRESERVED_AS_ORIGINAL_BUILD_HASH_NOT_NEW_HTML_VALIDATION",
              "new_html_browser_validation": "PENDING_ROOT_NATIVE_IDLE_NOTICE", "formal_progress": "0/280_UNCHANGED",
              "physical_e2e": "NOT_OBSERVED"}
    (OUT / "build_static_validation02.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"checks": len(checks), "output": manifest["output"], "runs": stats_rows,
                      "receipt_sha256": digest((OUT / "build_static_validation02.json").read_bytes())}, ensure_ascii=True))


if __name__ == "__main__":
    main()
