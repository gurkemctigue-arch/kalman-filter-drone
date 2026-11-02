"""Small Windows metadata/transaction fixtures; no native roots or flights."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import reliability_v4_publication as publication
from tools.diagnostics.reliability54_build01 import source_integrity


ROOT = Path(__file__).resolve().parents[1]
PAST = "2026-01-01T00:00:00+00:00"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return publication.binding(path)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "new_final"
        self.root.mkdir()
        self.original = {}
        for label, name in publication.PLANNING.items():
            value = {"status": "DRAFT_NOT_FROZEN_NOT_EXECUTED", "registration_utc": None,
                     "seeds": [1000, 1001], "resources": {"person": "unchanged", "car": "unchanged"}}
            if label == "core":
                value["navigation_acceptance"] = {"status": "REGISTERED", "registration_utc": PAST,
                    "maximum_base_link_distance_rmse_m": 1., "maximum_base_link_height_rmse_m": .4}
            if label == "extension":
                value["development_readiness"] = "PENDING"
            path = self.root / name
            write(path, value)
            # Preserve deliberately noncanonical whitespace and UTF-8 raw bytes.
            path.write_bytes(b' \n' + path.read_bytes())
            self.original[label] = path.read_bytes()
        self.evidence = self.base / "evidence"
        self.evidence.mkdir()
        self.audit = self.base / "audit/tools"
        self.audit.mkdir(parents=True)
        for name in ("reliability_v4_guard.py", "reliability_v4_register.py"):
            (self.audit / name).write_text("# inert test metadata only\n", encoding="utf-8")
        self.guard = SimpleNamespace(__file__=str(self.audit / "reliability_v4_guard.py"))

    def protocol(self, label):
        return publication.load(self.root / publication.PLANNING[label])

    def outcome(self, action, artifact, *, inputs=None, detail=None):
        directory = self.evidence / (action + "_assembly")
        directory.mkdir()
        artifact_binding = write(directory / "candidate.json", artifact)
        started = {"kind": "RELIABILITY_V4_REGISTRATION_ASSEMBLY_START", "action": action,
            "created_utc": PAST, "guard": publication.binding(self.guard.__file__),
            "registrar": publication.binding(self.audit / "reliability_v4_register.py"), "inputs": inputs or {}}
        write(directory / "started.json", started)
        value = {"schema_version": 1, "kind": "RELIABILITY_V4_REGISTRATION_ASSEMBLY_OUTCOME", "action": action,
            "created_utc": PAST, "status": "ASSEMBLED_AND_VALIDATED_NOT_EXECUTED", "canonical_files_modified": False,
            "formal_attempts_started": 0, "registrar": started["registrar"], "artifact": artifact_binding,
            "validated_bytes_sha256": artifact_binding["sha256"], "detail": detail or {}}
        return write(directory / "outcome.json", value)

    def test_protocol_changes_preserve_every_design_and_numerical_requirement(self):
        core, extension = self.protocol("core"), self.protocol("extension")
        new_core, new_extension = publication.protocol_candidates(core, extension, {"actual": "gate"}, PAST)
        self.assertEqual({key for key in new_core if new_core[key] != core.get(key)}, {"status", "registration_utc"})
        self.assertEqual({key for key in new_extension if new_extension[key] != extension.get(key)},
                         {"status", "registration_utc", "development_readiness"})
        self.assertEqual(core, self.protocol("core"))
        self.assertEqual(new_core["navigation_acceptance"], core["navigation_acceptance"])

    def test_protocol_refuses_registration_partial_state_and_unregistered_numerical_gate(self):
        for label, key, value in (("core", "status", "REGISTERED"), ("extension", "registration_utc", PAST),
                                  ("core", "navigation_acceptance", {"status": "DRAFT"})):
            values = {name: self.protocol(name) for name in ("core", "extension")}
            values[label][key] = value
            with self.subTest(label=label, key=key), self.assertRaises(ValueError):
                publication.protocol_candidates(values["core"], values["extension"], {}, PAST)

    def test_bound_refuses_changed_content_nonexact_schema_relative_path_and_bad_digest(self):
        good = write(self.evidence / "input.json", {"original": True})
        for candidate in ({**good, "extra": True}, {"path": "relative.json", "sha256": good["sha256"]},
                          {**good, "sha256": "a" * 64}, {**good, "sha256": "nan"}):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                publication.bound(candidate)

    def test_two_file_publication_keeps_all_three_exact_originals_and_preserves_replay(self):
        archives = publication.publish_transaction(self.root, {"core": b'{"new_core": true}\n',
            "extension": b'{"new_extension": true}\n'}, self.evidence)
        self.assertEqual(set(archives), set(publication.PLANNING))
        for label, item in archives.items():
            self.assertEqual(Path(item["path"]).read_bytes(), self.original[label])
        self.assertEqual((self.root / publication.PLANNING["replay"]).read_bytes(), self.original["replay"])

    def test_replay_publication_keeps_candidate_raw_bytes_and_only_archives_replay_draft(self):
        candidate = b' \n{"status" : "REGISTERED", "unicode": "\xe4\xb8\xad\xe6\x96\x87"}\r\n'
        archives = publication.publish_transaction(self.root, {"replay": candidate}, self.evidence)
        self.assertEqual(set(archives), {"replay"})
        self.assertEqual((self.root / publication.PLANNING["replay"]).read_bytes(), candidate)
        self.assertEqual(Path(archives["replay"]["path"]).read_bytes(), self.original["replay"])

    def test_second_file_failure_restores_first_and_retains_failure_recovery(self):
        original_replace = publication.replace_bytes
        calls = []
        def fail_second(path, data, expected):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("inert second replace failure")
            return original_replace(path, data, expected)
        with patch.object(publication, "replace_bytes", side_effect=fail_second), self.assertRaises(OSError):
            publication.publish_transaction(self.root, {"core": b'{}\n', "extension": b'[]\n'}, self.evidence)
        for label in publication.PLANNING:
            self.assertEqual((self.root / publication.PLANNING[label]).read_bytes(), self.original[label])
        recovery = publication.load(self.evidence / "recovery.json")
        self.assertTrue(recovery["all_restored"])
        self.assertFalse(recovery["atomic_across_files"])

    def test_failure_does_not_overwrite_unknown_concurrent_bytes_and_records_partial_recovery(self):
        original_replace = publication.replace_bytes
        def changed_second(path, data, expected):
            if path.name == Path(publication.PLANNING["extension"]).name:
                path.write_bytes(b"unknown concurrent edit\n")
                raise OSError("inert concurrent failure")
            return original_replace(path, data, expected)
        with patch.object(publication, "replace_bytes", side_effect=changed_second), self.assertRaises(OSError):
            publication.publish_transaction(self.root, {"core": b'{}\n', "extension": b'[]\n'}, self.evidence)
        self.assertEqual((self.root / publication.PLANNING["core"]).read_bytes(), self.original["core"])
        self.assertEqual((self.root / publication.PLANNING["extension"]).read_bytes(), b"unknown concurrent edit\n")
        self.assertFalse(publication.load(self.evidence / "recovery.json")["all_restored"])

    def test_repeat_evidence_directory_is_refused_before_second_publication(self):
        publication.publish_transaction(self.root, {"core": b'{}\n', "extension": b'[]\n'}, self.evidence)
        before = (self.root / publication.PLANNING["core"]).read_bytes()
        with self.assertRaises(FileExistsError):
            publication.publish_transaction(self.root, {"core": b'NEW'}, self.evidence)
        self.assertEqual((self.root / publication.PLANNING["core"]).read_bytes(), before)

    def test_replace_is_staged_on_planning_filesystem_and_wrong_old_sha_does_not_modify(self):
        path = self.root / publication.PLANNING["core"]
        with self.assertRaises(ValueError):
            publication.replace_bytes(path, b"new", "f" * 64)
        self.assertEqual(path.read_bytes(), self.original["core"])
        original_mkstemp = publication.tempfile.mkstemp
        staging = []
        def observed_temp(*args, **kwargs):
            staging.append(Path(kwargs["dir"]))
            return original_mkstemp(*args, **kwargs)
        with patch.object(publication.tempfile, "mkstemp", side_effect=observed_temp):
            publication.replace_bytes(path, b"new", publication.sha(path))
        self.assertEqual(staging, [path.parent])
        self.assertEqual(list(path.parent.glob("*.publication.*")), [])

    def test_assembly_checks_original_artifact_bytes_and_fixed_actual_tool_root(self):
        outcome = self.outcome("safety-summary", {"kind": "inert fixture only"})
        publication.assembly(outcome, "safety-summary", self.guard)
        original = publication.load(outcome["path"])
        original["validated_bytes_sha256"] = "a" * 64
        modified = write(Path(outcome["path"]), original)
        with self.assertRaises(ValueError):
            publication.assembly(modified, "safety-summary", self.guard)

    def test_assembly_refuses_wrong_guard_start_binding(self):
        outcome = self.outcome("replay-config", {})
        started_path = Path(outcome["path"]).with_name("started.json")
        started = publication.load(started_path)
        started["guard"]["sha256"] = "0" * 64
        write(started_path, started)
        with self.assertRaises(ValueError):
            publication.assembly(outcome, "replay-config", self.guard)

    def test_utc_refuses_naive_time(self):
        with self.assertRaises(ValueError):
            publication.utc("2026-01-01T00:00:00")

    def prepare_protocol_fixture(self):
        helper = self.root / "scripts/build_reliability_v4_probe_gate.py"
        helper.parent.mkdir()
        helper.write_text("# inert gate helper never imported\n", encoding="utf-8")
        hashes = {"scripts/build_reliability_v4_probe_gate.py": publication.sha(helper)}
        targets, gates = {}, {}
        development = self.base / "development"
        development.mkdir()
        for label, mode, count in (("core", "PROBE", 12), ("extension", "EXTENSION_PROBE", 16)):
            plan = {"mode": mode, "frozen_root": str(self.root), "source_hashes": hashes,
                "selected_seeds": [4], "trials": [{"id": str(i)} for i in range(count)], "plan_sha256": label}
            targets[label] = write(self.evidence / (label + "_target.json"), plan)
            dev = write(self.evidence / (label + "_dev.json"), {"frozen_root": str(development)})
            gate = {"bindings": {"matching": "immutable fixture"}, "generation": {
                "target_plan_path": targets[label]["path"], "target_plan_file_sha256": targets[label]["sha256"],
                "target_plan_sha256": label}, "probe_slots": [{"plan_path": dev["path"]}]}
            gates[label] = write(self.evidence / (label + "_gate.json"), gate)
        summary = {"kind": "RELIABILITY_V4_FINAL_SAFETY_SUMMARY", "result": "PASS", "created_utc": PAST,
            "bindings": {"matching": "immutable fixture"}, "slots": [{"result": "PASS"} for _ in range(4)]}
        safety = self.outcome("safety-summary", summary, inputs={"target_plan": targets["core"], "core_gate": gates["core"]})
        request = {"core_target": targets["core"], "extension_target": targets["extension"],
            "core_gate": gates["core"], "extension_gate": gates["extension"], "safety_assembly": safety}
        v4 = SimpleNamespace(read_slots=lambda plan: {t["id"]: {"status": "PENDING"} for t in plan["trials"]},
            validate_probe_gate=Mock(), validate_protocol=Mock(), validate_navigation_gates=Mock(),
            validate_extension_protocol=Mock(), extension_design=lambda p: {k: v for k, v in p.items()
                if k not in {"status", "registration_utc", "development_readiness", "results"}})
        builder = SimpleNamespace(target_snapshot=Mock(), verification_context=Mock(side_effect=lambda *args, **kwargs: {
            "branch": kwargs["extension"], "stamp": kwargs["registration_utc"]}))
        self.guard.load_runtime = Mock(return_value=SimpleNamespace(v4=v4))
        self.guard.import_file = Mock(return_value=builder)
        return request, v4, builder

    def test_protocols_use_both_actual_gate_branches_and_keep_originals_unchanged_during_prepare(self):
        request, v4, builder = self.prepare_protocol_fixture()
        candidates = publication.prepare_protocols(request, self.root, self.guard)
        self.assertEqual(set(candidates), {"core", "extension"})
        self.assertEqual([c.kwargs["extensions"] for c in v4.validate_probe_gate.call_args_list], [False, True])
        self.assertEqual(builder.target_snapshot.call_count, 4)
        for label in publication.PLANNING:
            self.assertEqual((self.root / publication.PLANNING[label]).read_bytes(), self.original[label])

    def test_protocols_refuse_final_root_reused_as_development_root(self):
        request, _, _ = self.prepare_protocol_fixture()
        write(self.evidence / "core_dev.json", {"frozen_root": str(self.root)})
        with self.assertRaisesRegex(ValueError, "Development runtime root"):
            publication.prepare_protocols(request, self.root, self.guard)

    def test_protocols_refuse_gate_generated_for_other_target(self):
        request, _, _ = self.prepare_protocol_fixture()
        gate = publication.load(request["extension_gate"]["path"])
        gate["generation"]["target_plan_file_sha256"] = "wrong"
        request["extension_gate"] = write(Path(request["extension_gate"]["path"]), gate)
        with self.assertRaisesRegex(ValueError, "another target"):
            publication.prepare_protocols(request, self.root, self.guard)

    def test_protocols_refuse_any_executed_target(self):
        request, v4, _ = self.prepare_protocol_fixture()
        v4.read_slots = lambda plan: {"already_executed": {"status": "PASS"}}
        with self.assertRaisesRegex(ValueError, "never have been executed"):
            publication.prepare_protocols(request, self.root, self.guard)

    def prepare_replay_fixture(self):
        publication_dir = self.evidence / "protocol_publication"
        publication_dir.mkdir()
        changed = publication.protocol_candidates(self.protocol("core"), self.protocol("extension"), {}, PAST)
        archives = publication.publish_transaction(self.root,
            {label: json.dumps(value).encode("utf-8") for label, value in zip(("core", "extension"), changed)}, publication_dir)
        receipt = {"kind": "RELIABILITY_V4_PLANNING_PUBLICATION_OUTCOME", "action": "protocols", "status": "PUBLISHED",
            "final_root": str(self.root), "audit_guard": publication.binding(self.guard.__file__), "original_drafts": archives,
            "canonical_files": {label: publication.binding(self.root / publication.PLANNING[label]) for label in ("core", "extension")}}
        protocol_binding = write(publication_dir / "outcome.json", receipt)
        core_plan = {"mode": "FORMAL", "frozen_root": str(self.root), "created_utc": PAST,
            "trials": [{"id": str(index)} for index in range(120)], "plan_sha256": "inert_fixture_digest"}
        core_binding = write(self.evidence / "formal_core.json", core_plan)
        candidate = {"status": "REGISTERED", "freeze_requirements": {
            "final_engineering_plan_path": core_binding["path"], "final_engineering_plan_file_sha256": core_binding["sha256"],
            "final_engineering_plan_digest": core_plan["plan_sha256"]}, "registration": {"registered_utc": PAST}}
        assembly_binding = self.outcome("replay-config", candidate, inputs={"core_plan": core_binding})
        archive = Path(assembly_binding["path"]).with_name("source_draft.original.json")
        archive.write_bytes(self.original["replay"])
        outcome = publication.load(assembly_binding["path"])
        outcome["detail"] = {"source_draft_archive": publication.binding(archive)}
        assembly_binding = write(Path(assembly_binding["path"]), outcome)
        v4 = SimpleNamespace(validate_plan=Mock(), verify_sources=Mock(),
            read_slots=Mock(return_value={str(i): {"status": "PENDING"} for i in range(120)}))
        replay = SimpleNamespace(validate_registered_config=Mock(), verify_registration_artifacts=Mock())
        self.guard.load_runtime = Mock(return_value=SimpleNamespace(v4=v4, replay=replay))
        return {"protocol_publication": protocol_binding, "core_plan": core_binding, "replay_assembly": assembly_binding}, v4, replay

    def test_replay_prepare_uses_original_assembly_bytes_and_both_existing_validators(self):
        request, v4, replay = self.prepare_replay_fixture()
        candidates = publication.prepare_replay(request, self.root, self.guard)
        artifact = publication.load(request["replay_assembly"]["path"])["artifact"]
        self.assertEqual(candidates, {"replay": Path(artifact["path"]).read_bytes()})
        replay.validate_registered_config.assert_called_once()
        replay.verify_registration_artifacts.assert_called_once()
        v4.verify_sources.assert_called_once()
        self.assertEqual((self.root / publication.PLANNING["replay"]).read_bytes(), self.original["replay"])

    def test_replay_prepare_refuses_any_started_formal_slot(self):
        request, v4, _ = self.prepare_replay_fixture()
        v4.read_slots.return_value["0"]["status"] = "FAIL"
        with self.assertRaisesRegex(ValueError, "precede every formal attempt"):
            publication.prepare_replay(request, self.root, self.guard)

    def test_replay_prepare_refuses_modified_original_draft_even_if_json_semantically_same(self):
        request, _, _ = self.prepare_replay_fixture()
        path = self.root / publication.PLANNING["replay"]
        path.write_bytes(path.read_bytes() + b" \n")
        with self.assertRaisesRegex(ValueError, "DRAFT bytes differ"):
            publication.prepare_replay(request, self.root, self.guard)

    def test_replay_prepare_refuses_wrong_actual_formal_plan_binding(self):
        request, _, _ = self.prepare_replay_fixture()
        outcome = publication.load(request["replay_assembly"]["path"])
        artifact = publication.load(outcome["artifact"]["path"])
        artifact["freeze_requirements"]["final_engineering_plan_file_sha256"] = "0" * 64
        outcome["artifact"] = write(Path(outcome["artifact"]["path"]), artifact)
        outcome["validated_bytes_sha256"] = outcome["artifact"]["sha256"]
        request["replay_assembly"] = write(Path(request["replay_assembly"]["path"]), outcome)
        with self.assertRaisesRegex(ValueError, "another formal core"):
            publication.prepare_replay(request, self.root, self.guard)


class CompleteMapContractTests(unittest.TestCase):
    """Synthetic Windows readlink/map doubles, not native symlink validation."""
    setUp = PublicationTests.setUp
    protocol = PublicationTests.protocol
    outcome = PublicationTests.outcome
    prepare_replay_fixture = PublicationTests.prepare_replay_fixture

    def keep_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def fixture(self):
        results = self.root / "results"
        archive = results / "freeze_validation/source_integrity"
        archive.mkdir(parents=True)
        for relative in (publication.INTEGRITY, "scripts/freeze_full_plan_workspace.sh"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / relative).read_bytes())
        entries = source_integrity.file_map(self.root)
        frozen_map = write(archive / "frozen_actual.json", {"frozen": str(self.root), "entries": entries})
        source = str(self.base / "independent_staging_source")
        before = write(archive / "source_before.json", {"source": source, "entries": entries})
        after = write(archive / "source_after.json", {"source": source, "entries": entries})
        link_target = str(results)
        report = {"status": "PASS", "scope": "RSYNC_FILTERED_SOURCE_PRE_POST_AND_COMPLETE_FROZEN_COPY_BYTES",
            "frozen": str(self.root), "source": source, "errors": [], "build_returncode": 0,
            "copy_identical": True, "source_unchanged": True,
            "source_pre_post": {"added": [], "changed": [], "missing": []},
            "frozen_copy": {"added": [], "changed": [], "missing": []},
            "maps": {"frozen_actual.json": frozen_map, "source_after.json": after}, "before": before,
            "generated_results_link": {"path": str(results), "target": link_target, "expected_store": str(results)},
            "actual_frozen_entries": len(entries), "actual_source_entries": len(entries), "expected_entries": len(entries)}
        report_binding = write(archive / "source_frozen_integrity.json", report)
        request = {"final_root": str(self.root), "freeze_report": report_binding, "frozen_map": frozen_map,
            "audit_guard": publication.binding(self.guard.__file__)}
        mapper = SimpleNamespace(validate_filters=source_integrity.validate_filters, differences=source_integrity.differences,
            RSYNC_EXCLUSIONS=source_integrity.RSYNC_EXCLUSIONS,
            file_map=lambda root: {**source_integrity.file_map(root), "results": {"kind": "symlink", "target": link_target}})
        real_is_symlink = Path.is_symlink
        self.keep_patch(patch.object(Path, "is_symlink", lambda path: path == results or real_is_symlink(path)))
        self.keep_patch(patch.object(publication.os, "readlink", return_value=link_target))
        self.keep_patch(patch.object(publication, "import_file", side_effect=lambda name, path:
            mapper if str(path).endswith("source_integrity.py") else self.guard))
        self.keep_patch(patch.object(publication, "AUDIT_GUARD_PATH", request["audit_guard"]["path"]))
        self.keep_patch(patch.object(publication, "AUDIT_GUARD_SHA256", request["audit_guard"]["sha256"]))
        return request

    def test_original_draft_complete_map_passes_only_with_same_bound_root_and_link(self):
        request = self.fixture()
        root, results, _, _, _, _ = publication.base_context(request, permitted_changes=[])
        self.assertEqual(root, self.root)
        self.assertEqual(results, self.root / "results")

    def test_full_map_refuses_nonplanning_change_added_file_and_missing_file(self):
        request = self.fixture()
        helper = self.root / publication.INTEGRITY
        original = helper.read_bytes()
        helper.write_bytes(original + b"# changed\n")
        with self.assertRaisesRegex(ValueError, "integrity helper"):
            publication.base_context(request, permitted_changes=[])
        helper.write_bytes(original)
        extra = self.root / "unexpected.py"
        extra.write_text("# added\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unexpected differences"):
            publication.base_context(request, permitted_changes=[])
        extra.unlink()
        (self.root / publication.PLANNING["replay"]).unlink()
        with self.assertRaisesRegex(ValueError, "unexpected differences"):
            publication.base_context(request, permitted_changes=[])

    def test_full_map_allows_exactly_two_then_three_named_planning_changes(self):
        request = self.fixture()
        for label in ("core", "extension"):
            path = self.root / publication.PLANNING[label]
            path.write_bytes(path.read_bytes() + b" \n")
        permitted = [publication.PLANNING[name] for name in ("core", "extension")]
        publication.base_context(request, permitted_changes=permitted)
        with self.assertRaises(ValueError):
            publication.base_context(request, permitted_changes=permitted + [publication.PLANNING["replay"]])
        path = self.root / publication.PLANNING["replay"]
        path.write_bytes(path.read_bytes() + b" \n")
        publication.base_context(request, permitted_changes=permitted + [publication.PLANNING["replay"]])

    def test_final_root_and_fixed_guard_cannot_be_substituted(self):
        request = self.fixture()
        alternate = deepcopy(request)
        alternate["audit_guard"] = publication.binding(self.audit / "reliability_v4_register.py")
        with self.assertRaisesRegex(ValueError, "already accepted"):
            publication.base_context(alternate, permitted_changes=[])
        alternate = deepcopy(request)
        alternate["final_root"] = str(self.base)
        with self.assertRaises(ValueError):
            publication.base_context(alternate, permitted_changes=[])

    def test_run_refuses_unknown_schema_before_any_root_check_or_output(self):
        request = {key: None for key in publication.FIELDS["protocols"]}
        request.update(schema_version=1, kind=publication.KIND, unexpected="forbidden")
        request_binding = write(self.evidence / "request.json", request)
        with patch.object(publication, "base_context") as check, self.assertRaises(ValueError):
            publication.run("protocols", request_binding["path"], request_binding["sha256"], self.evidence / "never_created")
        check.assert_not_called()
        self.assertFalse((self.evidence / "never_created").exists())

    def run_request(self):
        request = self.fixture()
        inert = write(self.evidence / "inert.json", {"evidence_scope": "METADATA_FIXTURE_ONLY"})
        request.update(schema_version=1, kind=publication.KIND)
        request.update({key: inert for key in publication.FIELDS["protocols"] - publication.COMMON})
        return write(self.evidence / "request.json", request)

    def test_run_requires_fresh_direct_results_child_and_rejects_nested_evidence(self):
        request = self.run_request()
        nested = self.root / "results/freeze_validation/new_publication"
        with patch.object(publication, "prepare_protocols") as prepare, self.assertRaises(ValueError):
            publication.run("protocols", request["path"], request["sha256"], nested)
        prepare.assert_not_called()
        self.assertFalse(nested.exists())

    def test_run_writes_real_transaction_outcome_and_will_not_reuse_changed_draft_root(self):
        request = self.run_request()
        output = self.root / "results/new_publication"
        candidates = {"core": b'{"status":"REGISTERED"}\n', "extension": b'{"status":"REGISTERED"}\n'}
        with patch.object(publication, "prepare_protocols", return_value=candidates):
            outcome = publication.run("protocols", request["path"], request["sha256"], output)
        self.assertEqual(outcome["status"], "PUBLISHED")
        self.assertEqual(outcome["formal_attempts_started"], 0)
        self.assertFalse(outcome["atomic_across_files"])
        self.assertEqual(set(outcome["original_drafts"]), set(publication.PLANNING))
        for label in ("core", "extension"):
            self.assertEqual((self.root / publication.PLANNING[label]).read_bytes(), candidates[label])
        with self.assertRaises(ValueError):
            publication.run("protocols", request["path"], request["sha256"], self.root / "results/another_output")

    def sidecar_fixture(self):
        request = self.fixture()
        root, _, entries, _, integrity, guard = publication.base_context(request, permitted_changes=[])
        replay_request, _, _ = self.prepare_replay_fixture()
        candidate = publication.prepare_replay(replay_request, self.root, self.guard)
        replay_dir = self.evidence / "replay_publication"
        replay_dir.mkdir()
        archives = publication.publish_transaction(self.root, candidate, replay_dir)
        replay_receipt = {"kind": "RELIABILITY_V4_PLANNING_PUBLICATION_OUTCOME", "action": "replay", "status": "PUBLISHED",
            "final_root": str(self.root), "audit_guard": publication.binding(self.guard.__file__), "original_drafts": archives,
            "canonical_files": {"replay": publication.binding(self.root / publication.PLANNING["replay"])}}
        replay_binding = write(replay_dir / "outcome.json", replay_receipt)
        validation = self.root / "results/freeze_validation"
        isolation = write(validation / "import_isolation.json", {"isolated": True, "root": str(self.root)})
        native = {"status": "PASS", "root": str(self.root), "reference": str(self.base / "development"),
            "scope": "ACTUAL_COLD_BUILD_COMPILER_ISOLATION_AND_GENERATED_CDR_NOT_FLIGHT_ACCEPTANCE",
            "original_freeze_and_current_bytes": {"report": request["freeze_report"]["path"],
                "report_sha256": request["freeze_report"]["sha256"], "original_map_sha256": request["frozen_map"]["sha256"],
                "current_frozen_bytes_unchanged": True}, "public_import_isolation": isolation}
        native_binding = write(validation / "native_build_supplement.json", native)
        admission = {"kind": "RELIABILITY_V4_FORMAL_ADMISSION", "final_root": str(self.root),
            "tool": publication.binding(self.guard.__file__), "state_directory": str(self.root / "results/new_guard_state")}
        admission_binding = write(self.evidence / "admission.json", admission)
        self.guard.check = Mock(return_value=SimpleNamespace(report={"result": "PASS", "capacity": {"pending_slots": 280}}))
        request.update(protocol_publication=replay_request["protocol_publication"], replay_publication=replay_binding,
            admission=admission_binding, native_validation=native_binding)
        current = integrity.file_map(root)
        current.pop("results")
        output = self.evidence / "sidecar"
        output.mkdir()
        return request, root, entries, current, integrity, guard, output

    def test_final_sidecar_binds_original_cold_evidence_and_exact_three_authorized_changes(self):
        args = self.sidecar_fixture()
        original_report = Path(args[0]["freeze_report"]["path"]).read_bytes()
        result = publication.sidecar(*args)
        report = publication.load(result["path"])
        self.assertEqual(report["differences_from_draft"], {"added": [], "missing": [],
            "changed": sorted(publication.PLANNING.values())})
        self.assertFalse(report["current_full_tree_equals_original_draft"])
        self.assertTrue(report["original_cold_build_evidence_retained"])
        self.assertEqual(report["native_validation"], args[0]["native_validation"])
        self.assertTrue(Path(report["original_source_before"]["path"]).is_file())
        self.assertTrue(Path(report["original_import_isolation"]["path"]).is_file())
        self.assertEqual(Path(args[0]["freeze_report"]["path"]).read_bytes(), original_report)
        self.assertTrue((args[-1] / "registered_final_map.json").is_file())

    def test_final_sidecar_refuses_original_native_failure(self):
        args = self.sidecar_fixture()
        native = publication.load(args[0]["native_validation"]["path"])
        native["status"] = "FAIL"
        args[0]["native_validation"] = write(Path(args[0]["native_validation"]["path"]), native)
        with self.assertRaisesRegex(ValueError, "native cold-build supplement"):
            publication.sidecar(*args)
        args[-2].check.assert_not_called()
        self.assertEqual(list(args[-1].iterdir()), [])

    def test_final_sidecar_refuses_initial_state_or_missing_pending_slot(self):
        args = self.sidecar_fixture()
        state = Path(publication.load(args[0]["admission"]["path"])["state_directory"])
        state.mkdir()
        with self.assertRaisesRegex(ValueError, "precede initial admission"):
            publication.sidecar(*args)
        state.rmdir()
        args[-2].check.return_value.report["capacity"]["pending_slots"] = 279
        with self.assertRaisesRegex(ValueError, "pending280"):
            publication.sidecar(*args)
        self.assertEqual(list(args[-1].iterdir()), [])

    def test_final_sidecar_refuses_source_change_during_guard_check(self):
        args = self.sidecar_fixture()
        def changed_during_check(path):
            (self.root / "unexpected.py").write_bytes(b"# changed during metadata check\n")
            return SimpleNamespace(report={"result": "PASS", "capacity": {"pending_slots": 280}})
        args[-2].check.side_effect = changed_during_check
        with self.assertRaisesRegex(ValueError, "Source changed during"):
            publication.sidecar(*args)
        self.assertEqual(list(args[-1].iterdir()), [])

    def test_final_sidecar_refuses_original_evidence_change_during_guard_check(self):
        args = self.sidecar_fixture()
        def changed_during_check(path):
            original = Path(args[0]["freeze_report"]["path"]).with_name("source_before.json")
            original.write_bytes(original.read_bytes() + b" \n")
            return SimpleNamespace(report={"result": "PASS", "capacity": {"pending_slots": 280}})
        args[-2].check.side_effect = changed_during_check
        with self.assertRaisesRegex(ValueError, "Bound input bytes/path changed"):
            publication.sidecar(*args)
        self.assertEqual(list(args[-1].iterdir()), [])


if __name__ == "__main__":
    unittest.main()
