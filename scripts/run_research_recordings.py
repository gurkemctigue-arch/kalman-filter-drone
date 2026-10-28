"""Reproduce offline extraction, paired estimator study, and detection review."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=["extract","replay","detection","all"],default="all")
    parser.add_argument("--reuse-images",action="store_true")
    parser.add_argument("--review-file",type=Path)
    parser.add_argument("--reuse-predictions",action="store_true")
    args=parser.parse_args()
    output=ROOT/"results/research_recordings"
    output.mkdir(parents=True,exist_ok=True)
    log_dir=ROOT/"results/research_validation";log_dir.mkdir(parents=True,exist_ok=True)
    names=[f"stage1_final_v2_{category}_{mode}" for category in ("person","car") for mode in ("velocity","position")]
    recordings=[output/name/"recording.json" for name in names]
    commands=[]
    if args.phase in ("extract","all"):
        for name in names:
            command=[sys.executable,str(ROOT/"scripts/extract_research_recording.py"),str(ROOT/"results"/name),
                     "--target-class","person" if "person" in name else "car","--output",str(output/name)]
            if args.reuse_images:
                command.append("--skip-images")
            commands.append((name+"_extraction",command))
    if args.phase in ("replay","all"):
        commands.append(("paired_replay",[sys.executable,str(ROOT/"scripts/run_recorded_research.py"),*map(str,recordings),
                                          "--output",str(ROOT/"results/recorded_estimator_research")]))
    if args.phase in ("detection","all"):
        command=[sys.executable,str(ROOT/"scripts/evaluate_detection_recordings.py"),*map(str,recordings),
                 "--output",str(ROOT/"results/detection_research")]
        if args.review_file:
            command.extend(["--review-file",str(args.review_file)])
        if args.reuse_predictions:
            command.append("--reuse-predictions")
        commands.append(("detection",command))
    records=[]
    for name,command in commands:
        print(f"Starting {name}",flush=True)
        with (log_dir/f"{name}.log").open("w") as log:
            process=subprocess.Popen(command,cwd=ROOT,env=dict(os.environ,PYTHONUNBUFFERED="1",OMP_NUM_THREADS="2"),
                                     stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            for line in process.stdout:
                log.write(line);log.flush();print(line,end="",flush=True)
            code=process.wait()
        record={"name":name,"command":command,"returncode":code,"finished_utc":datetime.now(timezone.utc).isoformat()}
        records.append(record)
        path=log_dir/f"offline_{args.phase}_commands.json"
        path.write_text(json.dumps(records,indent=2)+"\n")
        if code:
            raise SystemExit(code)


if __name__=="__main__":
    main()
