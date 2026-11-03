"""Create an isolated candidate from one exact fixed07 reducer, never patch it."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "humble54_pipeline_timing_bench01/reducer.py"
BASE_SHA = "628271811d1454b1521586cbe332d4d3636f24434ce783fb8f437a51edcb1351"


def main():
    raw = BASE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError("fixed07 reducer bytes differ; do not create candidate")
    source = raw.decode("utf-8")
    replacements = [
        ("from collections import Counter, defaultdict\n",
         "from collections import Counter, defaultdict\nfrom indexed_reduction import EventIndex, OutcomeIndex, read_events\n"),
        ("    edge_reports, associations = {}, {}\n",
         "    lookup = EventIndex(data)\n    by_index = {e[\"event_index\"]: e for e in events}\n    edge_reports, associations = {}, {}\n"),
        ("        by_index = {e[\"event_index\"]: e for e in events}\n", ""),
        ("        return _one([e for e in data if e[\"kind\"] == kind and e.get(key) == value], \"missing_or_ambiguous_\"+kind)",
         "        return _one(lookup.find(kind, key, value), \"missing_or_ambiguous_\"+kind)"),
        ("""            if any(e.get("process")==accepted["process"]
                   and accepted["recorded_monotonic_ns"] < e["recorded_monotonic_ns"] < project["recorded_monotonic_ns"]
                   and (e["kind"]=="navigation_clear" or e["kind"]=="navigation_update" and e.get("accepted") is True)
                   for e in data):""",
         "            if lookup.navigation_replaced(accepted, project):"),
        ("    opportunities = []\n", "    outcome_lookup = OutcomeIndex(outcomes)\n    opportunities = []\n"),
        ("        selected = [e for e in data if e[\"kind\"] == \"snapshot\" and e.get(\"rgb_token\") == rgb[\"image_token\"]]",
         "        selected = lookup.find(\"snapshot\", \"rgb_token\", rgb[\"image_token\"])"),
        ("        reached = [e for e in outcomes if e.get(\"rgb_token\") == rgb[\"image_token\"] and e[\"status\"] == \"CANDIDATE_SOFTWARE_LATENCY\"]",
         "        reached = outcome_lookup.find(rgb[\"image_token\"])"),
        ("""    for path in paths:
        raw = Path(path).read_bytes()
        bindings.append({"path":str(path), "bytes":len(raw), "sha256":hashlib.sha256(raw).hexdigest()})
        events.extend(json.loads(line) for line in raw.splitlines() if line)""",
         "    events.extend(read_events(paths, bindings))"),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError("replacement must match once: " + repr(before[:80]))
        source = source.replace(before, after)
    target = HERE / "reducer_candidate.py"
    target.write_text(source, encoding="utf-8", newline="\n")
    print(hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
