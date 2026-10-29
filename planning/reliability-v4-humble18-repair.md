# Humble17 observed failures and prospective repair

This is a development repair record. It is not a completed acceptance report,
protocol registration, or a formal held-out result. Formal seeds 1000–1009
remain unused.

## Preserved observations

The original Humble17 seed004 core matrix completed all 12 slots, with six
`EVALUATION_PENDING` and six `FAIL` records and no infrastructure failure.
Every original terminal record, recording and report is retained.

Two failures concern terminal paused gimbal feedback. The separate
`frozen_fullplan_v4_humble17_gimbal_audit01` source snapshot changes only three
offline scripts. It prospectively registers all six stage-three reevaluations,
including the originally passing slots, and requires `--selected-target` for
both multi-target slots. That audit does not repair flight behavior or turn an
original `FAIL` record into a `PASS`.

The car velocity and car midpoint slots each contain a genuine protective
`HOVER` after explicit reselection. Independent recorded images, depth, body
attitude and camera transforms show four consecutive incomplete car boxes at
the image's upper boundary. Body pitch peaks at approximately 12.5–12.8 degrees
as the aircraft accelerates to catch up. The camera optical axis consequently
tilts downward and clips the car roof. Navigation correctly rejects the
incomplete boxes, and the controller correctly rejects a measurement age
greater than 0.75 seconds. The image diagnosis is preserved under
`results/frozen_fullplan_v4_humble17/freeze_validation/car_images01/`.

The car crossing slot has a different cause. At source time 22.7 seconds,
YOLO reports both the complete car and a smaller roof box. The small box has
99.39% containment within the large box, with area ratio approximately 0.264.
Its apparent surface position differs by approximately 0.838 metres. The
existing track's Mahalanobis gate correctly rejects it (squared distance about
25.67 exceeds 9.21), but the unmatched box immediately creates another track.
Subsequent frames let both tracks compete for the same car, preserving an
artificial ambiguity even after only one complete detection remains. The task
eventually becomes lost and correctly cannot switch to the new track without
explicit selection. Independent images show no physical occlusion or image
boundary clipping in this window. Read-only descriptive sidecars are under
`freeze_validation/car_crossing_readonly_small01/` in the same result store.

Choosing the highest-confidence box is unsafe: the partial roof box sometimes
has a higher score than the complete box. Increasing the Mahalanobis threshold
or extending prediction time would obscure these failures.

## Candidate source changes

The stage-one and stage-three car controller configurations now use the
existing stage-two car acceleration limits: `[0.7, 0.7, 0.5]` metres per second
squared. Target speed limits, desired following distance and all freshness
limits are unchanged. This limits commanded pursuit acceleration; it is not a
proof of camera visibility under every attitude or target motion. Its effect
must be measured in new flights.

The implemented association repair defers the birth of an unsupported, smaller
nested detection near a same-class detection already supported by an existing
track. At least 95% of the smaller box must lie within the anchor box and its
area must be no more than 80% of the anchor's. When both surface positions are
available, separation beyond the existing 1.5-metre association distance domain
prevents deferral. The rule applies to `hybrid_3d` with ambiguity rejection.
It preserves raw detections and all real matching ambiguity. It does not assert
that the nested box represents the same physical object, merge existing track
identities, relax a gate, or add a measurement. A newly visible second object
can acquire a track when independently supported; an explicit selection must
remain possible. A genuinely new nearby object whose image remains nested can
therefore have delayed track birth; its raw detection remains visible in the
diagnostics. The new per-acquisition deferral indices and reasons are cleared
in projected telemetry snapshots.

Fifteen new behavior tests and forty-five existing tracking tests passed on
their first execution with one BLAS/OMP thread. A saved measurement/prior
fixture reproduces the original squared Mahalanobis distance of
25.66805528188335 and the complete-box distance of approximately 0.000632.
Other tests preserve actual one-to-many ambiguity, existing independent
tracks, explicit selection, independent image/depth separation, unique-mode
candidate counts, and the long-loss latch. Smooth subsequent positions used
in the behavior tests are explicitly synthetic; this is not a recorded replay
or a flight result. Independent source review found no deterministic defect
in the birth/diagnostic changes.

The frozen Humble18 source contains 517 files with canonical SHA256
`6fc1f6f040bad93ddf5dc749a6c6cea92dc1cf147371f43cb842f3cda099fc5b`.
The four ROS packages built in 10.0 seconds. All 1234 discovered Linux tests
passed in 38.699 seconds, with the existing two platform/document-tool skips;
the module and ament prefixes are isolated to that source. Its FastCDR cache,
compiler flags and library linkage were independently checked against Humble.
Two earlier external build-wrapper failures and their partial build products
are retained. Their corrections did not change the frozen source or system
dependencies. New flight validation remains required.

## Prospective verification

With the named source freeze, ROS build, import checks and Linux suite complete,
continue the new clean probes followed by the complete, predetermined two-class,
six-group seed004 core matrix. Do not retry
or relabel a failed old slot, replace a predetermined calibration source with
an easier diagnostic, or consume held-out seeds during development.

Only after the final-source core, four safety cases and sixteen condition
probes provide actual evidence can numerical gates and replay calibration be
registered. Recalculate storage from the actual final-source recordings before
admitting all 280 formal slots. The user's authorized game removal has provided
additional disk space; it does not replace the capacity admission calculation.
