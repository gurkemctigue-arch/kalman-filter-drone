"""Direct after07 navigation28 execution / sensor4 API collection, never admission.

Default describe is inert. Root must explicitly execute reviewed source in idle
native UAVHumble22 after the real final55 cold build. No WSL launcher, owner,
trigger, retry, flight, threshold change or image-review inference exists here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
FINAL = Path("/root/uav_tracking_fullplan_v4_final55")
GUARD = ROOT / "tools/staging/final55_offline_overlay_20261103/stage.py"
GUARD_SHA = "25a88f5ba369c918c5d891828b5e2434c61f75f33eb5485749f1ec0fda632268"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path):
    path = Path(path)
    require(path.stat().st_size <= 8 * 1024**2, "Small JSON/source input required")
    return json.loads(path.read_text(encoding="utf-8-sig"),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + value)))


def bound(path, expected=None):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), "Actual canonical ordinary input file required")
    resolved = path.resolve(strict=True)
    require(str(path) == str(resolved), "Input must already use its actual canonical path")
    actual = sha(path)
    require(expected is None or actual == expected, "Actual input SHA differs: " + str(path))
    return {"path":str(path), "sha256":actual}


def unchanged(bindings):
    for item in bindings:
        bound(item["path"], item["sha256"])


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True, allow_nan=False)
        handle.write("\n")


def fixed_module(path, expected, name):
    item = bound(path, expected)
    raw = Path(item["path"]).read_bytes()
    require(len(raw) <= 2 * 1024**2, "Small reviewed module required")
    module = types.ModuleType(name)
    module.__file__ = item["path"]
    sys.modules[name] = module
    exec(compile(raw, item["path"], "exec"), module.__dict__)
    return module


def context(target_path, target_sha):
    binding = bound(target_path, target_sha)
    target = load(target_path)
    root = Path(target["frozen_root"])
    require(root == FINAL and root.resolve(strict=True) == root, "Actual cold final55 root required")
    script = root / "scripts/build_reliability_v4_probe_gate.py"
    runner = root / "scripts/run_reliability_v4.py"
    bound(runner,target["source_hashes"]["scripts/run_reliability_v4.py"])
    cached = sys.modules.get("run_reliability_v4")
    require(cached is None or Path(cached.__file__).resolve() == runner,
            "Refusing a cached validator from another root")
    builder = fixed_module(script,target["source_hashes"]["scripts/build_reliability_v4_probe_gate.py"],
                           "after07_actual_final55_probe_builder")
    require(Path(builder.v4.__file__).resolve() == runner
            and sha(runner) == target["source_hashes"]["scripts/run_reliability_v4.py"],
            "Actually imported validator differs from the target root/source")
    _, actual, _ = builder.target_snapshot(target_path,extension=target["mode"] == "EXTENSION_PROBE")
    require(actual == target, "Target changed during loading")
    return builder,target,binding


def fresh_directory(output, protected):
    output = Path(output)
    require(output.is_absolute() and not output.exists() and not output.is_symlink()
            and output.parent.is_dir() and output.parent.resolve() == output.parent,
            "Fresh external output with an existing canonical parent required; no overwrite/retry")
    require(not any(output.is_relative_to(Path(root).resolve()) or Path(root).resolve().is_relative_to(output)
                    for root in protected), "Output must stay external to final/original source and evidence roots")
    output.mkdir(exist_ok=False)
    return output


def report_paths(path):
    path = Path(path)
    return [path, *(path.with_suffix("." + name + ".jsonl") for name in ("frames","raw_frames","message_frames"))]


def process_group(pgid):
    rows = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(")",1)[1].split()
            if int(fields[2]) == pgid:
                rows.append({"pid":int(path.name),"state":fields[0],"ppid":int(fields[1]),"start_ticks":int(fields[19])})
        except (FileNotFoundError,ProcessLookupError):
            continue
    return rows


def reap_group(pgid):
    # Popen exclusively owns the direct child's wait status. Only reap adopted
    # descendant zombies; waitpid(-pgid) could silently steal the real exit code.
    for row in process_group(pgid):
        if row["pid"] == pgid or row["ppid"] != os.getpid() or row["state"] not in {"Z","X"}:
            continue
        try:
            os.waitpid(row["pid"],os.WNOHANG)
        except ChildProcessError:
            pass


def clean_child(child, identity):
    actions=[]
    metadata_errors=[]
    # If the immediate /proc identity read failed, this exact Popen child has
    # never been waited. Keeping it unreaped holds its PID/PGID while TERM/KILL
    # target the group established by start_new_session=True. Do not restart it.
    held_unreaped=child.returncode is None
    def members():
        try:
            rows=process_group(child.pid)
        except BaseException as error:
            metadata_errors.append(repr(error))
            return None
        leader=next((row for row in rows if row["pid"] == child.pid),None)
        if identity is not None:
            require(leader is None or leader["start_ticks"] == identity["start_ticks"],
                    "Owned child identity changed; no signal sent")
        else:
            require(held_unreaped,"Missing identity and no unreaped direct-child ownership; no signal sent")
        return rows
    try:
        for sig,grace in ((signal.SIGTERM,10.0),(signal.SIGKILL,5.0)):
            rows=members()
            if rows == []:
                break
            try:
                os.killpg(child.pid,sig)
                actions.append(int(sig))
            except ProcessLookupError:
                pass
            deadline=time.monotonic()+grace
            while time.monotonic() < deadline:
                if identity is not None:
                    child.poll()
                try:
                    reap_group(child.pid)
                except BaseException as error:
                    metadata_errors.append(repr(error))
                if members() == []:
                    break
                time.sleep(0.05)
    finally:
        # Always wait the same actual handle, including acquisition/scan faults.
        # The direct child's wait status is never consumed by reap_group().
        # TERM10/KILL5 already supplied the full unchanged cleanup grace.
        child.wait(timeout=0.0)
    reap_group(child.pid)
    remaining=process_group(child.pid)
    require(not remaining,"Owned evaluator process group has residual members")
    return {"signals":actions,"remaining_group_members":remaining,"returncode":child.returncode,
            "identity_acquired":identity is not None,"metadata_errors":metadata_errors}


def run_command(command, log, timeout_s):
    require(isinstance(command,list) and command and all(isinstance(part,str) for part in command), "Exact argv list required")
    require(type(timeout_s) in {int,float} and math.isfinite(timeout_s) and timeout_s > 0,
            "Original positive finite evaluation timeout required")
    execution={"command":list(command),"started_utc":utc(),"finished_utc":None,
               "returncode":None,"error":None,"log":str(log),"log_sha256":None}
    child=None
    identity=None
    interrupted={}
    def stopped(number,_frame):
        raise InterruptedError("Signal " + str(number))
    try:
        for number in (signal.SIGINT,signal.SIGTERM):
            interrupted[number]=signal.signal(number,stopped)
        with Path(log).open("xb") as handle:
            child=subprocess.Popen(command,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
            rows=process_group(child.pid)
            identity=next(row for row in rows if row["pid"] == child.pid)
            execution["owned_child"]={"pid":child.pid,"pgid":child.pid,"start_ticks":identity["start_ticks"]}
            deadline=time.monotonic()+timeout_s
            while True:
                remaining=deadline-time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Original bound evaluation timeout exhausted")
                try:
                    execution["returncode"]=child.wait(timeout=min(0.5,remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            require(not process_group(child.pid),"Evaluator exited leaving group members")
            if execution["returncode"] != 0:
                execution["error"]="Evaluator returned " + str(execution["returncode"])
    except BaseException as error:
        execution["error"]=type(error).__name__ + ": " + str(error)
    finally:
        for number in interrupted:
            signal.signal(number,signal.SIG_IGN)
        try:
            if child is not None:
                try:
                    execution["cleanup"]=clean_child(child,identity)
                    execution["returncode"]=child.returncode
                except BaseException as error:
                    execution["cleanup_error"]=repr(error)
                    execution["error"]=execution["error"] or "Owned cleanup failed"
                if child.returncode is not None:
                    execution["returncode"]=child.returncode
            execution["finished_utc"]=utc()
            try:
                if Path(log).is_file():
                    execution["log_sha256"]=sha(log)
            except BaseException as error:
                execution["log_error"]=repr(error)
                execution["error"]=execution["error"] or "Closed log hash failed"
        finally:
            for number,handler in interrupted.items():
                signal.signal(number,handler)
    return execution


def navigation_preflight(builder,target,registration):
    v4=builder.v4
    require(registration.get("schema_version") == 1
            and registration.get("kind") == "RELIABILITY_V4_ALL28_NAVIGATION_REEVALUATION_REGISTRATION"
            and registration.get("evaluation_root") == target["frozen_root"]
            and registration.get("target_source_hashes") == target["source_hashes"]
            and registration.get("implementation_source_hashes") == {
                builder.SCRIPT:target["source_hashes"][builder.SCRIPT],builder.RUNNER:target["source_hashes"][builder.RUNNER]}
            and registration.get("evaluation_source_hashes") == v4.offline_source_hashes(target["source_hashes"]),
            "Prospective registration must bind this actual cold builder/validator/evaluator map")
    sources,planned,originals=builder.navigation_registration_inputs(target,
        [item["path"] for item in registration["source_plans"]],registration["report_basename"],require_new=True)
    require(sources == registration["source_plans"] and planned == registration["planned_evaluations"]
            and len(planned) == len(originals) == 28,"All 28 exact original commands and terminal/report bindings are required")
    registered=v4.utc_timestamp(registration["created_utc"])
    require(registered <= v4.utc_timestamp(v4.utc_now()),"Prospective registration is in the future")
    for previous,trial,saved in originals.values():
        require(v4.utc_timestamp(saved["finished_utc"]) <= registered,"Registration predates original completion")
    return sources,planned,originals


def target_unchanged(builder,target,target_binding):
    _,actual,_=builder.target_snapshot(Path(target_binding["path"]),extension=target["mode"] == "EXTENSION_PROBE")
    require(actual == target,"Original cold target/source/protocol snapshot changed during collection")


def run_navigation(builder,target,registration_binding,target_binding,output,*,invoke=run_command,producer_binding=None):
    registration=load(registration_binding["path"])
    sources,planned,originals=navigation_preflight(builder,target,registration)
    protected=[target["frozen_root"],*(Path(row["path"]).parent for row in sources),
               *(previous["frozen_root"] for previous,_,_ in originals.values()),
               *(trial["directory"] for _,trial,_ in originals.values())]
    output=fresh_directory(output,protected)
    inputs=[registration_binding,target_binding,producer_binding or bound(Path(__file__).resolve())]
    state={"status":"ERROR","kind":"ACTUAL_SERIAL_NAVIGATION28_PRODUCER_NOT_READINESS_OR_ADMISSION",
           "started_utc":utc(),"inputs":inputs,"executions":[],"formal_admission":False}
    complete=None
    try:
        for index,fixed in enumerate(planned):
            unchanged(inputs)
            require(all(not path.exists() and not path.is_symlink() for path in report_paths(fixed["report"])),
                    "Registered report/sidecar conflict; no overwrite or retry")
            previous,trial,saved=originals[fixed["plan_path"],fixed["slot_id"]]
            log=output/("%02d_%s.log" % (index,fixed["slot_id"]))
            print(json.dumps({"event":"ACTUAL_NAVIGATION_START","slot_id":fixed["slot_id"],"command":fixed["command"]}),flush=True)
            execution=invoke(fixed["command"],log,previous["evaluation_timeout_s"])
            state["executions"].append({"plan_path":fixed["plan_path"],"slot_id":fixed["slot_id"],"execution":execution})
            write_new(output/("%02d_execution.json" % index),state["executions"][-1])
            require(execution.get("command") == fixed["command"] and type(execution.get("returncode")) is int
                    and execution["returncode"] == 0 and execution.get("error") is None,
                    "Actual evaluator failed/interrupted; original failure and partial outputs retained")
            require(Path(fixed["report"]).is_file() and not Path(fixed["report"]).is_symlink(),"Actual report missing")
            print(json.dumps({"event":"ACTUAL_NAVIGATION_EXIT","slot_id":fixed["slot_id"],"returncode":execution["returncode"]}),flush=True)
        complete={"schema_version":1,"kind":"RELIABILITY_V4_ALL28_NAVIGATION_REEVALUATIONS",
            "prospective_registration":registration_binding,"source_plans":registration["source_plans"],
            "evaluation_source_hashes":registration["evaluation_source_hashes"],
            "registered_utc":registration["created_utc"],"created_utc":utc(),"slots":[]}
        for fixed,actual in zip(planned,state["executions"]):
            complete["slots"].append({"plan_path":fixed["plan_path"],"slot_id":fixed["slot_id"],
                "record_file_sha256":fixed["record_file_sha256"],"evaluation_overrides":[{
                    "kind":"navigation","original_report_sha256":fixed["original_report_sha256"],
                    "report":fixed["report"],"report_sha256":sha(fixed["report"]),
                    "evaluation_root":target["frozen_root"],"execution":actual["execution"]}]})
        path=output/"navigation_complete.json"
        write_new(path,complete)
        selected_mode="EXTENSION_PROBE" if target["mode"] == "EXTENSION_PROBE" else "PROBE"
        selected=[row["path"] for row in sources if row["mode"] == selected_mode]
        overrides,binding=builder.read_navigation_reevaluation_manifest(path,target,selected,
            extension=selected_mode == "EXTENSION_PROBE")
        require(len(overrides) == (16 if selected_mode == "EXTENSION_PROBE" else 12),"Original validator returned wrong gate subset")
        target_unchanged(builder,target,target_binding)
        unchanged(inputs)
        state.update(status="COMPLETED_ALL28_ORIGINAL_SCHEMA_VALIDATED_NOT_ENGINEERING_PASS",completion=binding,
                     original_validator_selected_overrides=len(overrides))
    except BaseException as error:
        state.update(error_type=type(error).__name__,error=repr(error))
    finally:
        state.update(finished_utc=utc(),attempted=len(state["executions"]),
            not_attempted=[{"plan_path":row["plan_path"],"slot_id":row["slot_id"]} for row in planned[len(state["executions"]):]])
        write_new(output/"terminal.json",state)
    return state


def run_sensor(builder,target,target_binding,contract_binding,manifest_binding,output,*,module_loader=fixed_module,producer_binding=None):
    declaration=target["protocol"][builder.v4.SENSOR_INPUT_EVIDENCE_FIELD]
    require(contract_binding == {key:declaration["contract"][key] for key in ("path","sha256")},
            "Use the actual cold target descriptor's exact contract, not a prepared/old substitute")
    contract=load(contract_binding["path"])
    module_binding=bound(declaration["module"]["path"],declaration["module"]["sha256"])
    inputs=[target_binding,contract_binding,manifest_binding,module_binding,producer_binding or bound(Path(__file__).resolve())]
    original=load(contract["source_plan"]["path"])
    output=fresh_directory(output,[target["frozen_root"],Path(contract["source_plan"]["path"]).parent,
        original["frozen_root"],*(trial["directory"] for trial in original["trials"])])
    state={"status":"ERROR","kind":"ACTUAL_SENSOR4_ORIGINAL_API_COLLECTION_NOT_READINESS_OR_ADMISSION",
           "started_utc":utc(),"inputs":inputs,"formal_admission":False,"image_review_created":False}
    try:
        module=module_loader(module_binding["path"],module_binding["sha256"],"after07_bound_actual_sensor_module")
        result=module.evaluate_development_manifest(Path(manifest_binding["path"]),contract)
        write_new(output/"sensor4_api_report.json",result)
        state["original_api_report"]=bound(output/"sensor4_api_report.json")
        require(result.get("status") in {"UPSTREAM_INPUT_INTERRUPTION_CORROBORATED","NOT_APPLICABLE"}
                and result.get("errors") == [] and result.get("missing_slot_ids") == []
                and len(result.get("per_slot",[])) == 4,"Original sensor4 API reports incomplete evidence")
        mapping,binding=builder.v4.read_sensor_input_evidence_manifest(target,Path(manifest_binding["path"]),
            [contract["source_plan"]["path"]])
        require(len(mapping) == 4,"Original runner did not independently bind all four fixed cells")
        write_new(output/"sensor4_runner_binding.json",binding)
        target_unchanged(builder,target,target_binding)
        unchanged(inputs)
        state.update(status="COMPLETED_SENSOR4_ORIGINAL_API_AND_RUNNER_VALIDATED_NOT_ENGINEERING_PASS",
                     original_api_status=result["status"],runner_binding=bound(output/"sensor4_runner_binding.json"))
    except BaseException as error:
        state.update(error_type=type(error).__name__,error=repr(error))
    finally:
        state["finished_utc"]=utc()
        write_new(output/"terminal.json",state)
    return state


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action")
    sub.add_parser("describe")
    for action in ("nav","sensor"):
        item=sub.add_parser(action)
        item.add_argument("--execute",action="store_true")
        item.add_argument("--reviewed-source-sha256")
        item.add_argument("--target-plan",type=Path,required=True)
        item.add_argument("--target-plan-sha256",required=True)
        item.add_argument("--output-directory",type=Path,required=True)
        if action == "nav":
            item.add_argument("--registration",type=Path,required=True)
            item.add_argument("--registration-sha256",required=True)
        else:
            item.add_argument("--contract",type=Path,required=True)
            item.add_argument("--manifest",type=Path,required=True)
            item.add_argument("--manifest-sha256",required=True)
    args=parser.parse_args(argv)
    if args.action in {None,"describe"} or not getattr(args,"execute",False):
        print(json.dumps({"status":"DESCRIBE_ONLY_NO_NATIVE_OR_INPUT_READ","actions":["nav","sensor"],
            "execution_requires":"explicit reviewed source, actual final55 target and artifact bindings, original idle SITL lock",
            "automatic_owner_trigger_retry_flight_or_admission":False},indent=2))
        return 0
    require(sys.platform == "linux" and os.environ.get("WSL_DISTRO_NAME") == "UAVHumble22",
            "Run explicitly in existing native UAVHumble22; no WSL launcher exists")
    require(args.reviewed_source_sha256 and sha(__file__) == args.reviewed_source_sha256,
            "Exact root-reviewed producer SHA required")
    guard=fixed_module(GUARD,GUARD_SHA,"after07_original_idle_guard")
    with guard.linux_idle_guard():
        import ctypes
        require(ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0) == 0,"Owned child subreaper setup failed")
        builder,target,target_binding=context(args.target_plan,args.target_plan_sha256)
        producer_binding=bound(Path(__file__).resolve(),args.reviewed_source_sha256)
        if args.action == "nav":
            state=run_navigation(builder,target,bound(args.registration,args.registration_sha256),target_binding,args.output_directory,
                                 producer_binding=producer_binding)
        else:
            state=run_sensor(builder,target,target_binding,bound(args.contract),bound(args.manifest,args.manifest_sha256),args.output_directory,
                             producer_binding=producer_binding)
        print(json.dumps({"status":state["status"],"terminal":str(args.output_directory/"terminal.json")},indent=2))
        return 0 if state["status"].startswith("COMPLETED_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
