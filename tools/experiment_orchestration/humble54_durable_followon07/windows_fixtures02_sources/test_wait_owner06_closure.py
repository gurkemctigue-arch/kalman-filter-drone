"""Small inert observer fixtures: no real handles, WSL or experiment calls."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("followon07", Path(__file__).with_name("wait_owner06_closure.py"))
f = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(f)


def context():
    identities = {name: {"pid": 100 + index, "start_token": "windows_filetime:fixture" + str(index), "role": name}
                  for index, name in enumerate(f.EXPECTED_HANDLES)}
    started = {key: "synthetic" for key in f.DESCRIPTION_FIELDS}
    started.update(pins={name: {"path": "D:/fixture/" + name, "sha256": "a" * 64}
                         for name in ("monitor", "collector", "gate", "chain_validator", "registered_profile", "entry", "plan")},
                   launcher_source={"path": "D:/fixture/launcher.py", "sha256": "b" * 64},
                   launcher_identity=identities["outer"], monitor_identity=identities["monitor"],
                   receipt_output="D:/synthetic/outer", monitor_output="D:/synthetic/monitor",
                   native_owner="/root/synthetic_owner06")
    native_identity = {"pid": 555, "boot_id": "fixture", "start_ticks": 66}
    early = {name: {"path": "D:/fixture/" + name, "sha256": "c" * 64}
             for name in ("windows_started.json", "first_monitor_state.json", "first_native_state.json", "registered_admission.json")}
    return {"identities": identities, "started": started, "observed": {"wsl_identity": identities["wsl"]},
            "native_start": {"owner_identity": native_identity}, "early_files": early,
            "admission": {"after_slot": "synthetic_slot1"},
            "prior_profile": {"schema_fixture": "preserved", "segments": [{"segment_id": "owner04", "original_fault": "preserved"}]}}


def actual_closed(ctx):
    native = {"status": "COLLECTION_FINISHED", "returncode": 0,
              "owner_identity": ctx["native_start"]["owner_identity"], "current_child": {"returncode": 0},
              "collected": [{"original_status": "FAIL"}]}
    outer = {"status": "COLLECTION_ENDED", "closure_verified": True, "errors": [],
             "native_collection_status": "COLLECTION_FINISHED", "launcher_identity": ctx["identities"]["outer"],
             "monitor_identity": ctx["identities"]["monitor"], "wsl_identity": ctx["identities"]["wsl"],
             "first_native_owner_identity": native["owner_identity"],
             "power_lease": {"released_utc": "2026-11-03T06:00:00+00:00", "release_return": 1}}
    for key in ("monitor_exit_code", "wsl_exit_code", "monitor_popen_wait_exit_code", "monitor_final_popen_wait_exit_code", "monitor_final_handle_exit_code", "wsl_final_handle_exit_code"):
        outer[key] = 0
    return outer, native


class FakeAPI:
    def __init__(self, exits=None, fail_bind=None, fail_poll=None):
        self.values = deepcopy(exits or {"monitor": [None, 0], "wsl": [None, 0], "outer": [None, None, 0]})
        self.fail_bind, self.fail_poll = fail_bind, fail_poll
        self.bound, self.closed, self.observed = [], [], {}

    def bind(self, identity):
        name = identity["role"]
        if name == self.fail_bind:
            raise ValueError("fixture creation identity changed")
        self.bound.append(name)
        return name

    def exit(self, handle):
        if handle == self.fail_poll:
            raise OSError("fixture invalid held handle")
        values = self.values[handle]
        code = values.pop(0) if len(values) > 1 else values[0]
        if code is not None:
            self.observed[handle] = code
        return code

    def close(self, handle):
        self.closed.append(handle)


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ctx = context()

    def test_default_does_not_read_context_acquire_handles_or_create_outputs(self):
        with patch.object(f, "load_context") as load, patch.object(f, "WindowsAPI") as api, patch.object(f.sys, "stdout", io.StringIO()):
            self.assertEqual(f.main([]), 0)
        load.assert_not_called()
        api.assert_not_called()

    def test_explicit_execution_cannot_acquire_handles_before_context_verification(self):
        with patch.object(f, "load_context", side_effect=ValueError("synthetic registration changed")), patch.object(f, "WindowsAPI") as api:
            with self.assertRaisesRegex(ValueError, "registration changed"):
                f.main(["--execute"])
        api.assert_not_called()

    def test_actual_immutable_early_start_and_history_are_bound_without_handles(self):
        with patch.object(f, "WindowsAPI") as api:
            ctx = f.load_context()
            self.assertEqual(ctx["admission"]["unknown_evidence_exceptions"], f.REGISTERED_UNKNOWN_EVIDENCE)
            self.assertEqual(len(ctx["prior_profile"]["segments"]), 2)
            self.assertEqual(ctx["admission"]["after_slot"], "person_extension_dropout_seed004")
            self.assertEqual(ctx["early_files"]["registered_admission.json"]["path"], ctx["started"]["registered_admission_unc"])
            with patch.object(f, "REGISTERED_UNKNOWN_EVIDENCE", {}):
                with self.assertRaisesRegex(ValueError, "Actual early identity/admission evidence differs"):
                    f.load_context()
        api.assert_not_called()

    def test_action_waits_for_all_three_actual_zero_exits(self):
        api = FakeAPI()

        def action(ctx, exits, output):
            self.assertEqual(set(api.observed), set(f.EXPECTED_HANDLES))
            self.assertTrue(all(value == 0 for value in api.observed.values()))
            self.assertEqual(api.closed, [])
            return {"status": "SYNTHETIC_FULL_CHAIN"}

        result = f.supervise(self.ctx, self.root / "out", api, pause=lambda _: None, action=action)
        self.assertEqual(result["status"], "CLOSURE_AUDIT_COMPLETED")
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(set(api.closed), set(f.EXPECTED_HANDLES))
        self.assertTrue(all(row["first_exit_observed_utc"] for row in result["handles"].values()))

    def test_nonzero_exit_never_generates_a_chain_or_retries(self):
        api = FakeAPI({"monitor": [None, 0], "wsl": [None, 2], "outer": [None, 2]})
        action = Mock()
        result = f.supervise(self.ctx, self.root / "out", api, pause=lambda _: None, action=action)
        self.assertEqual(result["returncode"], 2)
        self.assertIsNone(result["future_closure"])
        action.assert_not_called()
        self.assertEqual(api.bound, ["monitor", "wsl", "outer"])

    def test_already_exited_handle_cannot_be_claimed_as_live_acquisition(self):
        api = FakeAPI({"monitor": [0], "wsl": [None, 0], "outer": [None, 0]})
        action = Mock()
        result = f.supervise(self.ctx, self.root / "out", api, pause=lambda _: None, action=action)
        self.assertEqual(result["returncode"], 2)
        self.assertEqual(api.bound, ["monitor"])
        self.assertEqual(api.closed, ["monitor"])
        self.assertNotIn("alive_at_acquisition_observed_utc", result["handles"]["monitor"])
        action.assert_not_called()

    def test_metadata_fault_retains_handles_until_real_exit_but_never_runs_action(self):
        api = FakeAPI()
        action = Mock()
        real_publish = f.atomic_json
        failed = []

        def publish(path, value, **kwargs):
            if path.name == "state.json" and not failed:
                failed.append(True)
                raise PermissionError("synthetic publication fault")
            return real_publish(path, value, **kwargs)

        result = f.supervise(self.ctx, self.root / "out", api, pause=lambda _: None, action=action, publish=publish)
        self.assertEqual(result["returncode"], 2)
        self.assertEqual(set(api.observed), set(f.EXPECTED_HANDLES))
        self.assertEqual(set(api.closed), set(f.EXPECTED_HANDLES))
        action.assert_not_called()

    def test_changed_creation_identity_closes_only_acquired_handles(self):
        api = FakeAPI(fail_bind="wsl")
        action = Mock()
        result = f.supervise(self.ctx, self.root / "out", api, pause=lambda _: None, action=action)
        self.assertEqual(result["returncode"], 2)
        self.assertEqual(api.closed, ["monitor"])
        self.assertEqual(api.observed, {})
        action.assert_not_called()

    def test_unknown_handle_exit_is_preserved_and_not_assumed_zero(self):
        api = FakeAPI(fail_poll="monitor")
        action = Mock()
        result = f.supervise(self.ctx, self.root / "out", api, pause=lambda _: None, action=action)
        self.assertEqual(result["returncode"], 2)
        self.assertNotIn("monitor", result["exit_codes"])
        self.assertEqual(set(api.closed), set(f.EXPECTED_HANDLES))
        action.assert_not_called()

    def test_terminal_publication_failure_returns_failure(self):
        api = FakeAPI({name: [None, 0] for name in f.EXPECTED_HANDLES})
        real_publish = f.atomic_json

        def publish(path, value, **kwargs):
            if path.name == "terminal.json":
                raise OSError("synthetic terminal disk failure")
            return real_publish(path, value, **kwargs)

        with patch.object(f.sys, "stderr", io.StringIO()):
            result = f.supervise(self.ctx, self.root / "out", api, pause=lambda _: None,
                                 action=lambda *_: {"status": "SYNTHETIC_FULL_CHAIN"}, publish=publish)
        self.assertEqual(result["status"], "TERMINAL_PUBLICATION_FAILED_NO_RETRY")
        self.assertEqual(result["returncode"], 2)


class ChainAssemblyTests(unittest.TestCase):
    def test_prior_profile_is_exactly_preserved_without_future_placeholder_bindings(self):
        ctx = context()
        before = deepcopy(ctx["prior_profile"])
        roles = ("outer_terminal", "native_terminal", "monitor_final", "monitor_end", "events", "registered_entry_terminal")
        bindings = {name: {"path": "D:/synthetic/" + name, "sha256": "e" * 64} for name in roles}
        profile = f.full_profile(ctx, bindings)
        self.assertEqual(ctx["prior_profile"], before)
        self.assertEqual({**profile, "segments": profile["segments"][:-1]}, before)
        self.assertEqual(profile["segments"][-1]["closure_files"], bindings)
        self.assertEqual(profile["segments"][-1]["disposition"], "COMPLETED")
        bindings["native_terminal"]["sha256"] = None
        with self.assertRaisesRegex(ValueError, "Actual complete raw closure bindings"):
            f.full_profile(ctx, bindings)

    def test_stopped_or_unknown_original_closure_is_refused_and_algorithm_fail_is_kept(self):
        ctx = context()
        outer, native = actual_closed(ctx)
        before = deepcopy(native)
        exits = {name: 0 for name in f.EXPECTED_HANDLES}
        f.check_actual_close(ctx, exits, outer, native)
        self.assertEqual(native, before)
        self.assertEqual(native["collected"][0]["original_status"], "FAIL")
        for defect in ("stopped", "errors", "identity", "unknown_child", "lease", "nonzero"):
            with self.subTest(defect=defect):
                o, n, e = deepcopy(outer), deepcopy(native), dict(exits)
                if defect == "stopped":
                    o["status"] = "STOPPED_FAULT"
                elif defect == "errors":
                    o["errors"] = [{"error": "fixture"}]
                elif defect == "identity":
                    o["wsl_identity"]["start_token"] = "wrong"
                elif defect == "unknown_child":
                    n["current_child"]["returncode"] = None
                elif defect == "lease":
                    o["power_lease"]["release_return"] = 0
                else:
                    e["wsl"] = 2
                with self.assertRaises(ValueError):
                    f.check_actual_close(ctx, e, o, n)

    def test_closure_sha_is_measured_from_post_exit_originals_and_partial_chain_is_not_published(self):
        ctx = context()
        outer, native = actual_closed(ctx)
        outer_path = str(Path(ctx["started"]["receipt_output"]) / "terminal.json")
        native_path = ctx["started"]["native_owner"] + "/terminal.json"
        outer_raw, native_raw = json.dumps(outer).encode(), json.dumps(native).encode()

        def read(reference):
            return outer_raw if reference == outer_path else native_raw if reference == native_path else b"{}"

        chain = Mock()
        chain.v.local_small_read.side_effect = read
        chain.validate_chain.return_value = {"status": "OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION",
            "closed_ids": ["synthetic" + str(n) for n in range(16)], "pending_ids": [],
            "closed": [{"original_status": "FAIL"}] + [{"original_status": "PASS"} for _ in range(15)]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(f, "check_code"), patch.object(f, "load_chain", return_value=chain):
            out = Path(tmp)
            result = f.close_chain(ctx, {name: 0 for name in f.EXPECTED_HANDLES}, out)
            profile = json.loads((out / "full_owner_chain_profile.json").read_bytes())
            self.assertEqual(profile["segments"][-1]["closure_files"]["outer_terminal"]["sha256"], f.raw_sha(outer_raw))
            self.assertEqual(result["original_statuses"], {"PASS": 15, "FAIL": 1, "INCOMPLETE_EVIDENCE": 0})
            self.assertEqual(result["capacity_measurement"], "NOT_RUN")
        chain.validate_chain.return_value["pending_ids"] = ["remaining"]
        with tempfile.TemporaryDirectory() as tmp, patch.object(f, "check_code"), patch.object(f, "load_chain", return_value=chain):
            out = Path(tmp)
            with self.assertRaisesRegex(ValueError, "did not close all original sixteen"):
                f.close_chain(ctx, {name: 0 for name in f.EXPECTED_HANDLES}, out)
            self.assertEqual(list(out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
