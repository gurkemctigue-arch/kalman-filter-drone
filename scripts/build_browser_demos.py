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
import re
import shutil
import subprocess
from urllib.parse import quote


VIDEO_CLASSES = ("person", "car")
VIDEO_GROUPS = ("stage1_velocity", "stage1_position", "stage2_crossing",
                "stage3_midpoint", "stage3_active", "stage3_multi_active")
VIDEO_SEED = 1000
RECORDED_FILES = ("onboard.mp4", "run_config.json", "summary.json")
TERMINAL_STATUSES = {"PASS", "FAIL", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING",
                     "INFRASTRUCTURE_ERROR", "INTERRUPTED", "STOP", "STOPPED"}


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


def passthrough_arguments(executable: str) -> list[str]:
    """Select advertised timestamp passthrough support, including FFmpeg 4.4."""
    result = subprocess.run(
        [executable, "-hide_banner", "-h", "full"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=True, timeout=30,
    )
    help_text = result.stdout + "\n" + result.stderr
    if re.search(r"(?m)^\s*-fps_mode(?:\s|$)", help_text):
        return ["-fps_mode", "passthrough"]
    if re.search(r"(?m)^\s*-vsync(?:\s|$)", help_text):
        return ["-vsync", "0"]
    raise RuntimeError("FFmpeg does not advertise -fps_mode or -vsync timestamp passthrough")


def transcode_record(ffmpeg, ffprobe, timing_arguments, source, destination, record):
    """The same complete-recording conversion and timing check in both modes."""
    record["source_sha256"] = digest(source)
    expected = record.get("expected_source_sha256")
    if "files" in record:
        record["files"]["onboard.mp4"].update(content_hash_checked=True,
            content_hash_matches_original=None if expected is None else record["source_sha256"] == expected)
    if expected is not None and record["source_sha256"] != expected:
        raise ValueError("Recorded video differs from its original slot artifact hash")
    command = [ffmpeg, "-nostdin", "-n", "-v", "error", "-i", str(source),
               "-map", "0:v:0", "-an", "-c:v", "libx264", "-threads", "2",
               "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", *timing_arguments,
               "-movflags", "+faststart", str(destination)]
    record["argv"] = command
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
    if not matching:
        raise RuntimeError(f"Video frame/timing verification failed: {source.parent.name}")


def json_digest(value, excluded):
    return hashlib.sha256(json.dumps(
        {key: item for key, item in value.items() if key != excluded},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read_metadata(path):
    """Read only an explicitly named, bounded metadata object."""
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError(f"Missing or oversized metadata: {path}")
    data = path.read_bytes()
    value = json.loads(data.decode("utf-8-sig"), parse_constant=lambda token: (
        (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + token))))
    if not isinstance(value, dict):
        raise ValueError(f"Expected metadata object: {path}")
    return value, {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def selected_inventory(plan_path, selection_path):
    """Keep all twelve prospective slots; never discover or replace a source."""
    plan_path = plan_path.resolve(strict=True)
    selection_path = selection_path.resolve(strict=True)
    plan, plan_binding = read_metadata(plan_path)
    selection, selection_binding = read_metadata(selection_path)
    video = selection.get("video_selection", {})
    if (not isinstance(video, dict) or selection.get("selected_before_formal_execution") is not True
            or video.get("seed") != VIDEO_SEED or type(video.get("seed")) is not int
            or video.get("classes") != list(VIDEO_CLASSES)
            or video.get("groups") != list(VIDEO_GROUPS)
            or type(video.get("scheduled_clips")) is not int or video.get("scheduled_clips") != 12):
        raise ValueError("Selection must specify exactly the prospective seed1000 two-class/six-group twelve slots")
    if (plan.get("mode") != "FORMAL" or plan.get("plan_sha256") != json_digest(plan, "plan_sha256")
            or not isinstance(plan.get("output"), str)
            or not Path(plan.get("output", "")).is_absolute()
            or Path(plan["output"]).resolve() != plan_path.parent):
        raise ValueError("Actual FORMAL core plan with unchanged digest and native output path required")
    trials = plan.get("trials")
    if not isinstance(trials, list) or any(not isinstance(trial, dict) for trial in trials):
        raise ValueError("Plan must contain an explicit trial list")
    records = []
    for cls in VIDEO_CLASSES:
        for group in VIDEO_GROUPS:
            slot_id = f"{cls}_{group}_seed{VIDEO_SEED:03d}"
            row = {"slot_id": slot_id, "target_class": cls, "group": group, "seed": VIDEO_SEED,
                   "trial": None, "directory": None, "source": None, "slot_record": None,
                   "original_status": None, "original_engineering_result": None,
                   "original_outcome_scope": "Copied original verdict; not re-evaluated by this delivery tool",
                   "files": {}, "binding_checks": [], "unverifiable_fields": [],
                   "reasons": [], "transcode_eligible": False, "status": "UNAVAILABLE"}
            records.append(row)
            matches = [trial for trial in trials if trial.get("id") == slot_id]
            if len(matches) != 1:
                row["reasons"].append(f"Selected slot has {len(matches)} plan entries; exactly one is required")
                continue
            trial = matches[0]
            if any(trial.get(key) != value for key, value in (
                    ("target_class", cls), ("group", group), ("seed", VIDEO_SEED))):
                row["reasons"].append("Plan slot identity fields disagree with the prospective selection")
                continue
            if not isinstance(trial.get("directory"), str):
                row["reasons"].append("Selected plan has no explicit directory")
                continue
            directory = Path(trial["directory"])
            if not directory.is_absolute():
                row["reasons"].append("Selected plan directory is not an absolute native path")
                continue
            directory = directory.resolve()
            row.update(trial=trial.get("name"), directory=str(directory), source=str(directory / "onboard.mp4"))
            for name in RECORDED_FILES:
                path = directory / name
                row["files"][name] = {"path": str(path), "present": path.is_file()}
                if not path.is_file():
                    row["reasons"].append("Missing recorded evidence: " + name)
            slot_path = plan_path.parent / "slots" / (slot_id + ".json")
            row["slot_record_path"] = str(slot_path)
            try:
                slot, row["slot_record"] = read_metadata(slot_path)
            except (OSError, ValueError) as error:
                row["reasons"].append("Original terminal unavailable: " + str(error))
                slot = {}
            row.update(original_status=slot.get("status"),
                       original_engineering_result=slot.get("engineering_result"))
            bound = (slot.get("id") == slot_id and slot.get("name") == trial.get("name")
                     and slot.get("plan_sha256") == plan["plan_sha256"]
                     and slot.get("record_sha256") == json_digest(slot, "record_sha256"))
            row["slot_identity_bound"] = bound
            if not bound:
                row["reasons"].append("Original slot ID/name, plan digest or record digest binding is invalid")
            if (not isinstance(slot.get("status"), str) or slot["status"] not in TERMINAL_STATUSES
                    or not slot.get("finished_utc")):
                row["reasons"].append("No original terminal outcome; running/pending sources cannot be transcoded")
            hashes = slot.get("artifact_hashes", {})
            if not isinstance(hashes, dict):
                hashes = {}
            for name in RECORDED_FILES:
                expected = hashes.get(name)
                if name == "onboard.mp4" and expected is None:
                    row["unverifiable_fields"].append({"file": name, "field": "original_artifact_sha256",
                        "reason": "Original slot collector did not register a historical video SHA"})
                elif not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                    row["reasons"].append("Original slot artifact hash unavailable: " + name)
                row["files"][name]["original_artifact_sha256"] = expected
            row["expected_source_sha256"] = hashes.get("onboard.mp4")
            row["video_provenance_scope"] = (
                "Original slot video SHA available; content comparison deferred until transcoding"
                if row["expected_source_sha256"] else
                "Current complete recording mapped through plan and bound configuration/summary; historical video SHA absent")
            # Inventory never reads/hashes video content. That comparison runs before encoding.
            row["files"]["onboard.mp4"]["content_hash_checked"] = False
            for name in ("run_config.json", "summary.json"):
                if not row["files"][name]["present"]:
                    continue
                try:
                    metadata, binding = read_metadata(directory / name)
                    row["files"][name].update(binding)
                    if binding["sha256"] != hashes.get(name):
                        row["reasons"].append("Recorded metadata differs from original slot artifact hash: " + name)
                    fields = ("name", "target_class", "seed", "gazebo_seed", "stage", "scenario_kind",
                              "command_mode", "gimbal_mode", "target_mode", "association_mode")
                    for field in fields:
                        aliases = (("class_name", "target_class") if name == "summary.json" and field == "target_class"
                                   else ("scenario_kind", "scenario") if field == "scenario_kind" else (field,))
                        available = [alias for alias in aliases if alias in metadata]
                        if field not in trial or not available:
                            row["unverifiable_fields"].append({"file": name, "field": field,
                                "reason": "Absent from plan" if field not in trial else "Absent from recorded metadata"})
                            if name == "run_config.json" and field in ("name", "target_class", "seed", "scenario_kind"):
                                row["reasons"].append("Required configuration identity field unavailable: " + field)
                            if name == "summary.json" and field == "target_class":
                                row["reasons"].append("Recorded summary has no target class identity field")
                            continue
                        for alias in available:
                            matched = type(metadata[alias]) is type(trial[field]) and metadata[alias] == trial[field]
                            row["binding_checks"].append({"file": name, "field": alias, "plan_field": field,
                                "expected": trial[field], "actual": metadata[alias], "matched": matched})
                            if not matched:
                                row["reasons"].append(f"Recorded source identity mismatch: {name}:{alias}")
                            if field in slot and (type(slot[field]) is not type(metadata[alias]) or slot[field] != metadata[alias]):
                                row["reasons"].append(f"Recorded source disagrees with original slot field: {name}:{alias}")
                except (OSError, ValueError) as error:
                    row["reasons"].append(f"Unreadable recorded metadata {name}: {error}")
            row["transcode_eligible"] = not row["reasons"]
            if row["transcode_eligible"]:
                row["status"] = "NOT_TRANSCODED"
    return {"schema_version": 2, "source_plan": {**plan_binding, "plan_sha256": plan["plan_sha256"]},
            "source_selection": selection_binding, "scheduled_clips": 12, "trials": records}


def inventory_page(manifest, output, acceptance=None):
    """Render every selected slot, including missing and failed sources."""
    cards = []
    for row in manifest["trials"]:
        escape = lambda value: html.escape(str(value))
        verdict = f"原槽状态：{row['original_status']}；原工程结果：{row['original_engineering_result']}"
        reasons = "".join("<li>" + escape(reason) + "</li>" for reason in row["reasons"])
        if row.get("error"):
            reasons += "<li>" + escape(row["error"]) + "</li>"
        player = ""
        if row["status"] == "VERIFIED":
            player = '<video controls preload="metadata" src="' + escape(row["output"]) + '"></video>'
        cards.append('<article><h2>' + escape(row["slot_id"]) + '</h2><p>' + escape(verdict)
                     + '</p><p>视频交付状态：' + escape(row["status"]) + '</p><p>来源：'
                     + escape(row["directory"]) + '</p>' + player + '<ul>' + reasons + '</ul><p>未能逐字段核对：'
                     + escape(len(row["unverifiable_fields"])) + ' 项；具体字段与绑定见 manifest。</p></article>')
    verified = sum(row["status"] == "VERIFIED" for row in manifest["trials"])
    link = '' if acceptance is None else '<p><a href="' + html.escape(relative_url(acceptance, output), quote=True) + '">完整验收与失败历史</a></p>'
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>固定 12 槽视频来源台账</title><style>body{max-width:1060px;margin:30px auto;padding:0 18px;font:16px/1.6 system-ui;'
            'background:#f3f5f8;color:#172339}article{padding:20px;background:white;margin:20px 0}h2,p,li{overflow-wrap:anywhere}'
            'h2{font-size:18px}video{width:100%;max-height:600px}</style><h1>固定 12 槽视频来源台账</h1>'
            f'<p>事前固定选源：12 槽；已逐帧核对的播放副本：{verified}/12。</p>'
            '<p>文件存在、库存完成和转码 VERIFIED 均不代表飞行通过。缺片、失败和未终态槽保留；不替换种子，不补造视频。'
            '库存模式不读取视频内容，完整性及时间校验在实际转码时执行。</p>' + link + ''.join(cards)
            + '<p><a href="manifest.json">完整选源、原结果、缺失原因与来源绑定</a></p></html>')


def build_inventory_delivery(args, parser):
    try:
        manifest = selected_inventory(args.core_plan, args.selection)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    output = args.output.resolve()
    if output.exists() or any(row["directory"] is not None and (
            output == Path(row["directory"]) or Path(row["directory"]) in output.parents)
            for row in manifest["trials"]):
        parser.error("Choose a new delivery directory outside all original trial directories")
    acceptance = args.acceptance.resolve(strict=True) if args.acceptance else None
    manifest.update(created_utc=datetime.now(timezone.utc).isoformat(), tool_sha256=digest(Path(__file__)),
                    mode="INVENTORY_ONLY" if args.inventory_only else "INVENTORY_AND_TRANSCODE",
                    selection="All twelve prospective sources, irrespective of outcome; no substitutions",
                    time_semantics="Full original recordings; no trimming, interpolation or respeeding",
                    ffmpeg=None, frame_sync_arguments=None)
    output.mkdir(parents=True)

    def save():
        verified = sum(row["status"] == "VERIFIED" for row in manifest["trials"])
        manifest["counts"] = {"scheduled": 12,
            "transcode_eligible": sum(row["transcode_eligible"] for row in manifest["trials"]),
            "verified_copies": verified}
        manifest["video_delivery_complete"] = verified == 12
        manifest["delivery_status"] = "ALL12_COPIES_VERIFIED" if verified == 12 else "INCOMPLETE_VIDEO_DELIVERY"
        (output / "index.html").write_text(inventory_page(manifest, output, acceptance), encoding="utf-8")
        manifest["index_sha256"] = digest(output / "index.html")
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save()
    if not args.inventory_only and any(row["transcode_eligible"] for row in manifest["trials"]):
        ffmpeg, ffprobe = shutil.which(args.ffmpeg), shutil.which(args.ffprobe)
        if not ffmpeg or not ffprobe:
            parser.error("Inventory saved; ffmpeg and ffprobe are required for eligible video conversions")
        manifest["ffmpeg"] = subprocess.run([ffmpeg, "-version"], capture_output=True,
                                            text=True, check=True).stdout.splitlines()[0]
        timing = passthrough_arguments(ffmpeg)
        manifest["frame_sync_arguments"] = timing
        for number, row in enumerate(manifest["trials"], 1):
            if not row["transcode_eligible"]:
                continue
            row.update(status="ENCODING", output=f"demo_{number:02d}.mp4")
            save()
            try:
                transcode_record(ffmpeg, ffprobe, timing, Path(row["source"]), output / row["output"], row)
                row["source_sha256_after_transcode"] = digest(Path(row["source"]))
                row["source_unchanged_during_transcode"] = row["source_sha256_after_transcode"] == row["source_sha256"]
                if not row["source_unchanged_during_transcode"]:
                    raise RuntimeError("Source video changed during conversion")
            except Exception as error:
                row.update(status="FAILED", error=f"{type(error).__name__}: {error}")
                save()
                raise
            save()
    manifest["inventory_completed_utc"] = datetime.now(timezone.utc).isoformat()
    save()
    print(output / "index.html")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--trial", type=Path, action="append",
                        help="Explicit recorded trial directory; may be repeated")
    sources.add_argument("--core-plan", type=Path,
                         help="Actual FORMAL core plan for all twelve prospective video sources")
    parser.add_argument("--selection", type=Path,
                        default=Path(__file__).resolve().parents[1] / "planning/reliability-v4-delivery-selections.json")
    parser.add_argument("--inventory-only", action="store_true",
                        help="With --core-plan, retain all twelve sources without reading or encoding videos")
    parser.add_argument("--output", type=Path, required=True,
                        help="New delivery directory, never an original trial directory")
    parser.add_argument("--acceptance", type=Path,
                        help="Existing complete acceptance HTML to link")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    if args.core_plan:
        build_inventory_delivery(args, parser)
        return
    if args.inventory_only:
        parser.error("--inventory-only requires --core-plan")
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
    timing_arguments = passthrough_arguments(ffmpeg)
    output.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "tool_sha256": digest(Path(__file__)),
        "ffmpeg": version,
        "frame_sync_arguments": timing_arguments,
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
        try:
            transcode_record(ffmpeg, ffprobe, timing_arguments, source, destination, record)
            save_manifest()
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
