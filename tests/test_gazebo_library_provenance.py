"""Bounded owned-process ELF evidence; no simulator or bag is launched."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_gazebo_magnetic_libraries as provenance


def stat_text(pid, group=100, session=100, comm="gz (server)", start=4242):
    fields = ["0"] * 24
    fields[0:4] = ["S", "1", str(group), str(session)]
    fields[19] = str(start)
    return f"{pid} ({comm}) " + " ".join(fields)


class ProcParsingTests(unittest.TestCase):
    def test_stat_handles_parentheses_and_extracts_epoch_and_scope(self):
        item = provenance.parse_stat(stat_text(123))
        self.assertEqual((item["pid"], item["process_group"], item["session"], item["start_ticks"]), (123, 100, 100, 4242))
        self.assertEqual(item["comm"], "gz (server)")

    def test_maps_select_only_magnetic_libraries_and_preserve_deleted_and_space(self):
        text = ("1-2 r-xp 0 00:01 12 /opt/with\\040space/libgz-sim8-magnetometer-system.so.8.15.0\n"
                "2-3 r-xp 0 00:01 13 /opt/libgz-sensors8-magnetometer.so.8.2.2 (deleted)\n"
                "3-4 r-xp 0 00:01 14 /opt/unrelated.so\n"
                "4-5 rw-p 0 00:00 0 [heap]\n")
        items = provenance.parse_magnetic_maps(text)
        self.assertEqual(len(items), 2)
        self.assertIn("with space", items[0]["mapped_path"])
        self.assertTrue(items[1]["deleted"])

    def test_retry_is_bounded_and_does_not_retry_hash_conflicts(self):
        with patch.object(provenance, "capture", side_effect=[provenance.LibrariesNotReady("loading"), {"verified": True}]) as capture, patch.object(provenance.time, "sleep") as sleep:
            self.assertEqual(provenance.capture_ready(100)["capture_attempts"], 2)
            self.assertEqual(capture.call_count, 2); sleep.assert_called_once_with(.1)
        with patch.object(provenance, "capture", side_effect=ValueError("hash mismatch")) as capture:
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                provenance.capture_ready(100)
            capture.assert_called_once()

    def test_both_audited_environment_registrations_are_accepted(self):
        for filename, distro in (("gazebo_magnetic_runtime.json", "jazzy"),
                                 ("gazebo_magnetic_runtime_humble22.json", "humble")):
            item = provenance.load_registration(provenance.ROOT / "config" / filename)
            self.assertEqual(item["environment"]["ros_distro"], distro)

    def test_equal_source_hash_does_not_authorize_an_unknown_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            item = provenance.load_registration(provenance.REGISTRATION)
            item["source_registration"]["gazebo_sensors_commit"] = "a" * 40
            registration = Path(temporary) / "registration.json"
            registration.write_text(json.dumps(item))
            with self.assertRaisesRegex(ValueError, "outside the audited variants"):
                provenance.load_registration(registration)

    def test_registration_must_be_audited_and_match_declared_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            registration = Path(temporary) / "registration.json"
            item = provenance.load_registration(provenance.REGISTRATION)
            item["libraries"]["gazebo_sim"]["package_file_md5_matches"] = False
            registration.write_text(json.dumps(item))
            with self.assertRaisesRegex(ValueError, "audit is incomplete"):
                provenance.load_registration(registration)
            item = provenance.load_registration(provenance.REGISTRATION)
            item["environment"] = {"os_id": "ubuntu", "os_version": "22.04", "ros_distro": "humble"}
            registration.write_text(json.dumps(item))
            with self.assertRaisesRegex(ValueError, "conflicts with its declared environment"):
                provenance.load_registration(registration)


@unittest.skipUnless(os.name == "posix", "Linux device/inode proc fixture")
class OwnedProcFixtureTests(unittest.TestCase):
    def fixture(self, base):
        proc = base / "proc"; proc.mkdir()
        for pid, children in ((100, "101 200"), (101, "")):
            root = proc / str(pid); (root / "task" / str(pid)).mkdir(parents=True)
            (root / "stat").write_text(stat_text(pid))
            (root / "task" / str(pid) / "children").write_text(children)
            (root / "maps").write_text("")
        escaped = proc / "200"; escaped.mkdir(); (escaped / "stat").write_text(stat_text(200, group=200, session=200))
        unrelated = proc / "999"; unrelated.mkdir(); (unrelated / "maps").write_text("must not be read")
        registration = provenance.load_registration(provenance.REGISTRATION)
        lines = []
        for index, (kind, name) in enumerate(provenance.KINDS.items(), 1):
            mapped_path = registration["libraries"][kind]["path"]
            library = proc / "101/root" / mapped_path.lstrip("/")
            library.parent.mkdir(parents=True, exist_ok=True)
            data = b"\x7fELF owned fixture " + kind.encode(); library.write_bytes(data)
            st = library.stat()
            device = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}"
            lines.append(f"{index:x}000-{index+1:x}000 r-xp 0 {device} {st.st_ino} {mapped_path}")
            registration["libraries"][kind]["sha256"] = hashlib.sha256(data).hexdigest()
        (proc / "101/maps").write_text("\n".join(lines + lines))
        manifest = base / "registration.json"; manifest.write_text(json.dumps(registration))
        return proc, manifest

    def test_only_owned_descendant_maps_are_read_and_segments_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc, manifest = self.fixture(Path(temporary))
            original_read, read_paths = provenance.read_bounded, []
            def read(path, limit):
                read_paths.append(str(path))
                if "/999/" in str(path) or str(path).endswith("/200/maps"):
                    raise AssertionError("unrelated process maps must not be read")
                return original_read(path, limit)
            with patch.object(provenance, "read_bounded", side_effect=read):
                result = provenance.capture(100, proc_root=proc, registration_json=manifest)
            self.assertTrue(result["verified"])
            self.assertEqual(len(result["actual_loaded_libraries"]), 2)
            self.assertEqual({p["pid"] for p in result["observed_processes"]}, {100, 101})
            self.assertEqual(result["excluded_descendants"][0]["pid"], 200)
            self.assertFalse(any("/999/" in path for path in read_paths))
            self.assertEqual(result["registration_sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
            self.assertEqual(result["registration_path"], str(manifest.resolve()))

    def test_registered_binary_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc, manifest = self.fixture(Path(temporary))
            registration = json.loads(manifest.read_text())
            registration["libraries"]["gazebo_sim"]["sha256"] = "a" * 64
            manifest.write_text(json.dumps(registration))
            with self.assertRaisesRegex(ValueError, "registered environment"):
                provenance.capture(100, proc_root=proc, registration_json=manifest)

    def test_equal_binary_hash_at_an_unregistered_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc, manifest = self.fixture(Path(temporary))
            registration = json.loads(manifest.read_text())
            old_path = Path(registration["libraries"]["gazebo_sim"]["path"])
            registration["libraries"]["gazebo_sim"]["path"] = str(old_path.parent / "other" / old_path.name)
            manifest.write_text(json.dumps(registration))
            with self.assertRaisesRegex(ValueError, "registered environment"):
                provenance.capture(100, proc_root=proc, registration_json=manifest)

    def test_nonowned_leader_and_bounded_process_count_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc, manifest = self.fixture(Path(temporary))
            with self.assertRaisesRegex(ValueError, "bound exceeded"):
                provenance.capture(100, proc_root=proc, registration_json=manifest, process_limit=1)
            (proc / "100/stat").write_text(stat_text(100, group=99))
            with self.assertRaisesRegex(ValueError, "own registered session"):
                provenance.capture(100, proc_root=proc, registration_json=manifest)


if __name__ == "__main__":
    unittest.main()
