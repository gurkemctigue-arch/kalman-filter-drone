# V4 prospective acceptance contract

This is an acceptance schema, not a registered performance result. The checked-in
protocol still has no chosen numeric performance thresholds. Formal plan creation
and execution reject that draft until the numeric gates are `REGISTERED`.

Every trial requires exactly one `source_clock`, `native_startup`, `surface_flight`, and `navigation`
report. Multi-target groups additionally require `selected_target_safety` and
`physical_identity`; stage-three groups also require `gimbal`. Omitted, duplicate,
unexpected, malformed, changed, or contradictory evidence cannot pass. A source
clock report must independently pass, including source/helper provenance, raw /
diagnostic / adapted counts, clock-domain validity and vehicle-frame continuity.

Navigation acceptance checks the full physical interval, 0.1 s sampling grid,
positive denominators and physical-metric counts, post-calibration KF denominator,
count/coverage agreement, nonnegative finite RMSE, and the existing transient
definitions. Settling and censoring must agree; a settled suffix must last at
least the existing 3 s through the recorded end, use the existing distance/height
bands and have a finite feasible start. This adds schema validation, not relaxed
safety gates or newly chosen performance thresholds.

The prospective v4 flight command explicitly uses `takeoff_mode=px4_native`.
The archived CLI and supervisor parameters must agree, with a 3 m takeoff,
`MIS_TAKEOFF_ALT=3`, `COM_TAKEOFF_ACT=0` and `SENS_IMU_MODE=1` in the saved PX4 startup overrides.
The supervisor, startup-readiness helper, PX4 startup shell and flight shell are
required frozen critical sources. This preserves the original source-clock and
target freshness gates; startup qualification precedes Offboard activation.
An independent `native_startup` evaluator audits the recorded PX4 takeoff
command, command/mode ordering, ground qualification, settled final handoff and
the visual task starting after handoff. It uses nine fixed named checks and its
own source provenance; replaying an online readiness helper is not its evidence.

Physical identity uses `conservative_task_time_identity`, the fixed 0.1 s cells
from the first explicit REQUEST to the last recorded `/clock`. Unknown intervals,
missing streams, task boundaries, and unconfirmed requests retain their time
denominator. Per-task counts, UUIDs, confirmation times and aggregate ratios must
agree. Any wrong identity in this time audit or the legacy diagnostic-frame audit
fails. An unconfirmed request also fails. The legacy frame coverage is retained
as `diagnostic_frame_identity`, without substituting it for full-task coverage.

## Development gate before formal trials

The final development gate requires a complete 2-class x 6-group probe matrix,
with at least one independently completed immutable slot per cell. These are
development seeds, not held-out seeds 1000–1009. The script rereads each frozen
PROBE plan, terminal record, its saved artifact hashes, actual runtime
configuration, magnetic runtime/library evidence and evaluation reports, and
recomputes acceptance using the prospectively registered thresholds. A Boolean
claim such as `{"development_probe": true}` is insufficient.

The gate JSON has this shape. Hash maps are complete actual hashes, not the
illustrative empty maps below. Do not copy the example as passing evidence.

```json
{
  "schema_version": 2,
  "result": "PASS",
  "ready_for_formal_reliability_v4": true,
  "checks": {
    "source_clock_independently_passed": true,
    "native_startup_independently_passed": true,
    "magnetic_runtime_and_loaded_libraries_verified": true,
    "base_link_navigation_performance_passed": true,
    "full_task_physical_identity_passed": true,
    "gimbal_feedback_passed": true,
    "original_safety_gates_preserved": true
  },
  "bindings": {
    "flight_source_hashes": {},
    "evaluation_source_hashes": {},
    "model_hashes": {},
    "magnetic_runtime_manifest_sha256": "ACTUAL_SHA256",
    "magnetic_library_registration_sha256": "ACTUAL_SHA256",
    "navigation_acceptance_sha256": "ACTUAL_CANONICAL_GATES_DIGEST"
  },
  "probe_slots": [
    {
      "plan_path": "/frozen/probe/results/matrix/plan.json",
      "plan_file_sha256": "ACTUAL_FILE_SHA256",
      "slot_id": "person_stage1_velocity_seed000",
      "record_file_sha256": "ACTUAL_TERMINAL_RECORD_FILE_SHA256"
    }
  ]
}
```

`flight_source_hashes` is produced by the runner's function of that name. It
excludes the runner and explicit offline evaluator sources/helpers, while
retaining flight scripts, online modules, configuration, worlds, models, and
runtime manifests. Evaluator and model maps, both runtime/library hashes and the
canonical registered-gates digest are bound separately. The gate file itself is
hashed and frozen inside the formal plan; modifying it later invalidates the plan.

An offline evaluator can advance after a preserved probe flight. Source-clock,
native-startup, navigation and physical-identity reports can be reevaluated under a separately
identified revision using new filenames inside the same trial directory. A slot
reference may then include `evaluation_overrides`, a list of objects containing
`kind`, `report`, `report_sha256`, `evaluation_root`, and the actual `execution`
record. Only these four reports carry the required independent script/helper
provenance. Their hashes must match the formal evaluation revision. Original
reports and terminal records remain unchanged; flight-critical sources, model
weights, safety parameters and runtime bindings must still match the final
formal flight revision. This does not authorize a retry of a failed slot.

The unit tests create explicitly labelled `ORCHESTRATION_FIXTURE_ONLY` evidence.
The real external runtime verifier rejects that evidence. No real gate file or
registered numeric threshold is generated by those tests.
