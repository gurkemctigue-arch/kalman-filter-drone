"""Small temporary JSONL only; fake POSIX flock on Windows, no native execution."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_closed_trace as cli
import test_candidate


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FakeFcntl:
    LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8
    def __init__(self, busy=False):
        self.calls, self.busy = [], busy
    def flock(self, descriptor, mode):
        self.calls.append(mode)
        if mode == self.LOCK_EX | self.LOCK_NB and self.busy:
            raise BlockingIOError("synthetic busy lock")


def synthetic_inputs(root):
    traces = root / "closed_native"
    traces.mkdir()
    events = test_candidate.fixture()[0]
    paths = []
    for role in cli.ROLES:
        path = traces / (role + ".jsonl")
        path.write_bytes(b"\n".join(json.dumps(row).encode() for row in events if row["process"] == role))
        paths.append(path)
    reduced = test_candidate.baseline.reduce_files(paths, probe_path=test_candidate.PROBE, begin_ns=1000, end_ns=9000)
    original = {"native_complete": True, "error": None, "cleanup_errors": [],
                "process_exit_codes": {role: 0 for role in cli.ROLES if role != "monitor"},
                "owned_group_status": {str(i): {"leader_returncode": 0, "group_still_present": False} for i in range(5)}, **reduced}
    summary = traces / "native_summary.json"
    summary.write_text(json.dumps(original), encoding="utf-8")
    source_map = test_candidate.BASE / "source_sha256_windows07.json"
    candidate = HERE / "reducer_candidate.py"
    args = SimpleNamespace(summary=str(summary), summary_sha256=digest(summary), trace_root=str(traces), output=str(root / "verified"),
                           source_map=str(source_map), source_map_sha256=digest(source_map),
                           candidate=str(candidate), candidate_sha256=digest(candidate), helper_sha256=digest(HERE / "indexed_reduction.py"),
                           probe=str(test_candidate.PROBE), probe_sha256=digest(test_candidate.PROBE), cli_sha256=digest(Path(cli.__file__)))
    lock = root / "existing_machine.lock"
    lock.write_bytes(b"preserve-lock-content")
    return args, original, lock


class VerifyTests(unittest.TestCase):
    def run_execute(self, args, lock, fake=None):
        fake = fake or FakeFcntl()
        with patch.object(cli, "LOCK_PATH", lock), patch.dict(sys.modules, {"fcntl": fake}), redirect_stdout(io.StringIO()):
            status = cli.execute(args)
        return status, fake

    def test_default_describe_reads_no_inputs_or_lock(self):
        with patch.object(cli, "execute", side_effect=AssertionError("execute forbidden")), \
             patch.object(cli, "bound_file", side_effect=AssertionError("input read forbidden")), \
             redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(cli.main([]), 0)
        self.assertEqual(json.loads(stream.getvalue())["default"], "DESCRIBE_ONLY_NO_INPUT_READ_OR_OUTPUT_WRITE")

    def test_complete_synthetic_verification_and_all_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args, original, lock = synthetic_inputs(root)
            before = {path: path.read_bytes() for path in Path(args.trace_root).iterdir()}
            lock_before = lock.read_bytes()
            status, fake = self.run_execute(args, lock)
            self.assertEqual(status, 0)
            self.assertEqual(fake.calls, [fake.LOCK_EX | fake.LOCK_NB, fake.LOCK_UN])
            receipt = json.loads((Path(args.output) / "verification_receipt.json").read_text(encoding="utf-8"))
            result = json.loads((Path(args.output) / "candidate_result.json").read_text(encoding="utf-8"))
            self.assertTrue(receipt["success"] and receipt["all_bound_inputs_unchanged"])
            self.assertEqual(set(receipt["field_exact_equality"]), set(cli.REDUCER_FIELDS))
            self.assertEqual(result, {key: original[key] for key in cli.REDUCER_FIELDS})
            self.assertEqual(receipt["original_summary"]["sha256"], args.summary_sha256)
            self.assertEqual(len(receipt["original_traces"]), 6)
            self.assertGreater(receipt["performance"]["wall_ns"], 0)
            self.assertGreaterEqual(receipt["performance"]["process_cpu_ns"], 0)
            self.assertIn("THIS_OFFLINE", receipt["performance"]["scope"])
            self.assertFalse(receipt["native_started"] or receipt["native_terminal_modified"])
            self.assertEqual(lock.read_bytes(), lock_before)
            self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_missing_or_busy_lock_does_not_create_outputs_or_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _, lock = synthetic_inputs(Path(directory))
            lock.unlink()
            with self.assertRaises(FileNotFoundError):
                self.run_execute(args, lock)
            self.assertFalse(lock.exists() or Path(args.output).exists())
            lock.write_bytes(b"existing")
            busy = FakeFcntl(busy=True)
            with self.assertRaises(BlockingIOError):
                self.run_execute(args, lock, busy)
            self.assertEqual(busy.calls, [busy.LOCK_EX | busy.LOCK_NB])
            self.assertFalse(Path(args.output).exists())

    def test_wrong_summary_source_and_raw_hashes_refuse_before_output(self):
        for field in ("summary_sha256", "source_map_sha256", "candidate_sha256", "helper_sha256", "probe_sha256", "cli_sha256", "raw_trace"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                args, _, lock = synthetic_inputs(Path(directory))
                if field == "raw_trace":
                    path = Path(args.trace_root) / "monitor.jsonl"
                    content = path.read_bytes()
                    path.write_bytes(content.replace(b"same-linux-boot", b"tame-linux-boot"))
                else:
                    setattr(args, field, "0" * 64)
                with self.assertRaises(ValueError):
                    self.run_execute(args, lock)
                self.assertFalse(Path(args.output).exists())

    def test_output_is_new_and_disjoint_from_every_protected_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            args, _, _ = synthetic_inputs(Path(directory))
            trees = (Path(args.trace_root), Path(args.summary).parent, Path(args.source_map).parent,
                     Path(args.candidate).parent, Path(args.probe).parent)
            for tree in trees:
                with self.subTest(tree=tree):
                    args.output = str(tree / "must-not-create-synthetic-output")
                    with self.assertRaises(ValueError):
                        cli.output_path(args)
                    self.assertFalse(Path(args.output).exists())
            args.output = str(Path(directory))
            with self.assertRaises(ValueError):
                cli.output_path(args)

    def test_nonclosed_original_is_rejected(self):
        for key, value in (("native_complete", False), ("error", "original failure"), ("cleanup_errors", ["failure"]),
                           ("owned_group_status", {}), ("process_exit_codes", {"detector": 0})):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                args, original, lock = synthetic_inputs(Path(directory))
                original[key] = value
                Path(args.summary).write_text(json.dumps(original), encoding="utf-8")
                args.summary_sha256 = digest(args.summary)
                with self.assertRaises(ValueError):
                    self.run_execute(args, lock)
                self.assertFalse(Path(args.output).exists())

    def test_mismatch_keeps_full_candidate_result_and_failure_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            args, original, lock = synthetic_inputs(Path(directory))
            original["candidate_command_count"] += 1
            Path(args.summary).write_text(json.dumps(original), encoding="utf-8")
            args.summary_sha256 = digest(args.summary)
            status, _ = self.run_execute(args, lock)
            self.assertEqual(status, 2)
            receipt = json.loads((Path(args.output) / "verification_receipt.json").read_text(encoding="utf-8"))
            self.assertFalse(receipt["success"] or receipt["field_exact_equality"]["candidate_command_count"])
            self.assertTrue((Path(args.output) / "candidate_result.json").is_file())

    def test_exact_comparison_keeps_json_number_and_boolean_types(self):
        self.assertNotEqual(cli.canonical(True), cli.canonical(1))
        self.assertNotEqual(cli.canonical(1.0), cli.canonical(1))
        self.assertEqual(cli.canonical({"a": 1, "b": 2}), cli.canonical({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
