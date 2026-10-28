"""Create browser-playable copies of explicitly selected recorded videos.

Original recordings, frame rate and timestamps remain intact. This delivery
tool never reads bags, evaluates a flight, selects successful trials or edits
the frozen research source. Run after the simulator has stopped.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import quote


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def probe(executable: str, path: Path) -> dict:
    result = subprocess.run(
        [executable, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_frames",
         "-show_entries", "stream=codec_name,width,height,avg_frame_rate,nb_read_frames:format=duration:frame=best_effort_timestamp_time",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if len(streams) != 1 or int(streams[0].get("nb_read_frames", 0)) < 1:
        raise ValueError(f"No decoded video frames: {path}")
    timestamps = [float(frame["best_effort_timestamp_time"]) for frame in data.get("frames", [])]
    if len(timestamps) != int(streams[0]["nb_read_frames"]) or any(
            right <= left for left, right in zip(timestamps, timestamps[1:])):
        raise ValueError(f"Missing or nonmonotonic decoded video timestamps: {path}")
    return {**streams[0], "duration_s": float(data["format"]["duration"]),
            "relative_frame_timestamps_s": [value - timestamps[0] for value in timestamps]}


def relative_url(path: Path, directory: Path) -> str:
    import os
    return quote(Path(os.path.relpath(path, directory)).as_posix(), safe="/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, action="append", required=True,
                        help="Explicit recorded trial directory; may be repeated")
    parser.add_argument("--output", type=Path, required=True,
                        help="New delivery directory, never an original trial directory")
    parser.add_argument("--acceptance", type=Path,
                        help="Existing complete acceptance HTML to link")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    ffmpeg = shutil.which(args.ffmpeg)
    ffprobe = shutil.which(args.ffprobe)
    if not ffmpeg or not ffprobe:
        parser.error("ffmpeg and ffprobe are required; install them in the delivery environment")
    trials = [path.resolve(strict=True) for path in args.trial]
    if len(set(trials)) != len(trials):
        parser.error("Each trial must be listed once")
    for trial in trials:
        for name in ("onboard.mp4", "run_config.json", "summary.json"):
            if not (trial / name).is_file():
                parser.error(f"Missing recorded evidence: {trial / name}")
    output = args.output.resolve()
    if output.exists():
        parser.error("Output already exists; preserve it and choose a new delivery directory")
    if any(output == trial or trial in output.parents for trial in trials):
        parser.error("Delivery output must be outside original trial directories")
    version = subprocess.run([ffmpeg, "-version"], capture_output=True,
                             text=True, check=True).stdout.splitlines()[0]
    output.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "tool_sha256": digest(Path(__file__)),
        "ffmpeg": version,
        "selection": "Explicit operator-selected illustrations; never a success-rate sample",
        "time_semantics": "Original recorded frame rate and source overlays; no trimming, interpolation or respeeding",
        "trials": [],
    }
    manifest_path = output / "manifest.json"

    def save_manifest() -> None:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")

    save_manifest()
    cards = []
    for number, trial in enumerate(trials, 1):
        source = trial / "onboard.mp4"
        destination = output / f"demo_{number:02d}.mp4"
        record = {
            "trial": trial.name, "source": str(source),
            "source_sha256": digest(source), "status": "ENCODING",
            "source_config_sha256": digest(trial / "run_config.json"),
            "source_summary_sha256": digest(trial / "summary.json"),
            "output": destination.name,
        }
        manifest["trials"].append(record)
        save_manifest()
        command = [ffmpeg, "-nostdin", "-n", "-v", "error", "-i", str(source),
                   "-map", "0:v:0", "-an", "-c:v", "libx264", "-threads", "2",
                   "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-fps_mode", "passthrough",
                   "-movflags", "+faststart", str(destination)]
        record["argv"] = command
        try:
            before = probe(ffprobe, source)
            subprocess.run(command, check=True)
            after = probe(ffprobe, destination)
            matching = (after["codec_name"] == "h264"
                        and before["width"] == after["width"]
                        and before["height"] == after["height"]
                        and int(before["nb_read_frames"]) == int(after["nb_read_frames"])
                        and Fraction(before["avg_frame_rate"]) == Fraction(after["avg_frame_rate"])
                        and abs(before["duration_s"] - after["duration_s"]) <= .1
                        and all(abs(left - right) <= .0001 for left, right in zip(
                            before["relative_frame_timestamps_s"], after["relative_frame_timestamps_s"])))
            record.update(source_video=before, delivered_video=after,
                          output_sha256=digest(destination),
                          status="VERIFIED" if matching else "TIMING_OR_FRAME_MISMATCH")
            save_manifest()
            if not matching:
                raise RuntimeError(f"Video frame/timing verification failed: {trial.name}")
        except Exception as error:
            record.update(status="FAILED", error=f"{type(error).__name__}: {error}")
            save_manifest()
            raise
        title = html.escape(trial.name)
        original = html.escape(relative_url(source, output), quote=True)
        summary = html.escape(relative_url(trial / "summary.json", output), quote=True)
        cards.append(f'<article><h2>{title}</h2><video controls preload="metadata">'
                     f'<source src="{destination.name}" type="video/mp4"></video>'
                     f'<p><a href="{original}">原始录制</a> · '
                     f'<a href="{summary}">运行摘要</a></p></article>')
        print(f"Verified {number}/{len(trials)}: {trial.name}", flush=True)
    acceptance = ""
    if args.acceptance:
        target = args.acceptance.resolve(strict=True)
        acceptance = '<p><a href="' + html.escape(relative_url(target, output), quote=True) + '">完整验收与失败历史</a></p>'
    document = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>三阶段仿真演示</title><style>'
                'body{max-width:1060px;margin:32px auto;padding:0 18px;background:#f3f5f8;'
                'color:#172339;font:16px/1.65 system-ui,"Microsoft YaHei",sans-serif}'
                'article{background:white;padding:20px;margin:24px 0;border-radius:10px}'
                'h2{font-size:17px;overflow-wrap:anywhere}video{width:100%;max-height:600px;background:#111}'
                'a{color:#135ca9}</style><h1>三阶段仿真演示</h1>'
                '<p>本页提供实际录制的 H.264 浏览器播放副本，保持原有帧数、时长和时间标注。'
                '演示是明确选取的样例；全部试验的通过率、失败、身份未知及统计结论请查看完整验收与研究报告。</p>'
                + acceptance + ''.join(cards)
                + '<p><a href="manifest.json">视频来源、转换命令与 SHA-256</a></p></html>')
    (output / "index.html").write_text(document, encoding="utf-8")
    manifest["index_sha256"] = digest(output / "index.html")
    manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
    save_manifest()
    print(output / "index.html")


if __name__ == "__main__":
    main()
