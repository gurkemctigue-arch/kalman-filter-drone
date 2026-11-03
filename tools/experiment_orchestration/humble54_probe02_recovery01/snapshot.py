"""Snapshot named small recovery records byte for byte; no native tasks."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]
DEST = Path(__file__).resolve().parent / "originals"
EXTERNAL = Path("D:/WSL/UAVHumble22-validation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", action="store_true")
    args = parser.parse_args()
    if not args.snapshot:
        print("PREPARED_NOT_EXECUTED")
        return
    assert not DEST.exists()
    sources = {}
    def add(source, target):
        source = Path(source)
        assert source.is_file() and source.stat().st_size < 8 * 1024 * 1024
        assert target not in sources
        sources[target] = source
    old = ROOT / "results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe01_matrix"
    new = ROOT / "results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix"
    add(old / "plan.json", "probe01/plan.json")
    slots = sorted((old / "slots").glob("*.json"))
    assert len(slots) == 16
    for source in slots:
        add(source, "probe01/slots/" + source.name)
    add(new / "plan.json", "probe02/plan.json")
    for name in ("state.json", "terminal.json"):
        add(ROOT / "results/diagnostics/humble54_pending_collection03" / name, "collector03/" + name)
    for folder in ("humble54_orphan_flight_observer01", "humble54_probe02_collection04_preflight01"):
        source_folder = ROOT / "results/project_progress" / folder
        add(source_folder / "end_summary.json", folder + "/end_summary.json")
        for log in source_folder.glob("command_*.log"):
            add(log, folder + "/" + log.name)
    for folder in ("humble54_extension16_probe02_registration01", "humble54_interrupted08_closure01"):
        add(EXTERNAL / folder / "outcome.json", folder + "/outcome.json")
    add(EXTERNAL / "run_humble54_pending_probe02_one03.sh", "entry03.original.sh")
    probe = ROOT / "results/diagnostics/humble54_drvfs_sharing_actual01"
    for source in probe.rglob("*"):
        if source.is_file():
            add(source, "drvfs_actual01/" + source.relative_to(probe).as_posix())
    assert hashlib.sha256((new / "plan.json").read_bytes()).hexdigest() == "1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54"
    assert json.loads((ROOT / "results/diagnostics/humble54_pending_collection03/terminal.json").read_bytes())["status"] == "STOPPED_FAULT"
    inventory = {}
    DEST.mkdir()
    for relative, source in sources.items():
        destination = DEST / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        raw = source.read_bytes()
        assert raw == destination.read_bytes()
        inventory[relative] = {"source": str(source), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    receipt = {"scope": "BYTE_EXACT_RECOVERY_METADATA_SNAPSHOT_NOT_FLIGHT_OR_READINESS",
               "created_utc": datetime.now(timezone.utc).isoformat(),
               "files": inventory, "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (DEST.parent / "manifest.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "SNAPSHOT_CREATED", "files": len(inventory), "bytes": sum(row["bytes"] for row in inventory.values())}))


if __name__ == "__main__":
    main()
