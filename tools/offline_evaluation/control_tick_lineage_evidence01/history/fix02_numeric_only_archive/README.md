# Recorded control-tick lineage, frozen offline method v1

This independent standard-library tool reuses the **original** `timing_v2`
`events.jsonl` and its SHA-bound `context.json`. It never reads a native bag,
imports ROS or project modules, changes online files, creates a prospective
registration, selects successful seeds, or writes into source/trial/plan roots.
It is not an extension of the old timing report kind and must not impersonate
that dashboard attachment. Do not modify the old timing tool or old reports.

The endpoint label is **采集→控制循环取时（tick开始）source_sim**. The
controller assigns the command/status header from its clock sample at the start
of `_step`, before `controller.update()` and before publishing. This is neither
publication completion nor PX4 receipt/execution nor physical wall-clock E2E.
A unique recorded constraint solution does not observe the subscriber callback
and does not establish complete callback causality.

```
python -B control_tick_lineage.py describe
python -B control_tick_lineage.py analyze --events ORIGINAL/events.jsonl \
  --context ORIGINAL/context.json --context-sha256 ORIGINAL_CONTEXT_SHA \
  --output EXISTING_EXTERNAL_DIRECTORY/new_control_tick_lineage.json
python -B -m unittest discover -s tools/offline_evaluation/control_tick_lineage_v1 \
  -p test_control_tick_lineage.py -v
```

`describe` identifies a frozen offline method, **not a formal registration**.
Before actual analysis, lock this tool/test artifact and its supported source
bindings by SHA in the delivery evidence. The exact supported source digests
include `navigation_estimator.py` in addition to the existing timing context
source list. Differing source bytes are rejected; inspection of new source
requires an explicit new reviewed artifact. The original timing exporter/test
digests are fixed in this tool. File analysis verifies the original source,
receipts, metadata, selected/native-topic counts, inputs and tool hashes before
and after analysis. It does not re-read bag payloads to prove exporter honesty.
Job logs are SHA-bound but their content is not used here; worker wall FPS stays
unobserved. The original recorder timestamp domain remains unverified.

Every original `/tracking/command` message and command decode error remains in
the denominator, including inactive/failsafe, duplicates and malformed records.
The report lists per-command reasons, candidate counts and event indices,
coverage, and quantiles for the known subset only. Unknown latency is `null`,
never zero. Multiple native states remain UNKNOWN even when they share the same
accepted image. Missing/duplicate or malformed lineage, epoch change/source
regression, missing required streams, relevant decode errors and unsupported
numeric payloads retain uncertainty. An active diagnostic without its separate
native state also prevents a unique conclusion for that track.

Matching uses unique command/status tick+track, unique native/diagnostic
header+track+UUID+state, finite payload comparison, exact binary32 covariance
and age serialization, and unique detector `(clock_epoch, acquisition_ns)`.
The accepted image comes only from `output_measurement_source_s`; the latest
processed `acquisition_s` can refer to a rejected measurement and is not used.
Source seconds must have exactly one supported integer-nanosecond preimage.
The actual node conversion `float(sec) + float(nanosec) * 1e-9` is used for
output, accepted-measurement and detector source stamps. The independently
sampled `output_publication_s` uses its actual `ns * 1e-9` conversion. These
conversions are checked separately; a value from another conversion is not
silently substituted. The supported integer domain remains `0 <= ns < 2**53`.
Both conversions are nondecreasing on that domain, including second boundaries.
A full-domain lower-bound search finds the first exact preimage; the next
integer mapping to the same value makes the sample UNKNOWN. This avoids
assuming that a rounded centre or round trip proves a unique inverse. In
particular, above `2**23` seconds some adjacent integer nanosecond stamps have
the same binary64 seconds value. Unique large stamps remain supported, while
ambiguous stamps, negative zero and nonfinite/out-of-domain inputs are rejected.
Native age must equal the exact implemented difference of diagnostic output
and accepted source seconds, followed by native binary32 serialization.

The status-age check executes the controller's actual arithmetic:

```
F32(float(native_prediction_age_s) + max(0, tick_ns - native_header_ns) * 1e-9)
```

It then compares binary32 **bits** with the recorded status. No broad tolerance,
nearest message, first match, recorder-time causality, or truth identity is used.
The native payload position/velocity consistency check retains the established
absolute `1e-8` source-export policy; it is not used as an age matching tolerance.
Negative zero in wire-age/covariance matching, NaN, infinity and overflows are
unsupported and yield UNKNOWN.

Candidates are indexed by track and accepted integer acquisition time. The
candidate window is derived from the recorded status's binary32 rounding bin,
one full binary32 native-age spacing, and conservative binary64 arithmetic
error bounds. Exact formula and payload checks follow the index query. This is
an arithmetic error bound, not a configurable latency/nearest window. Native
future headers recorded before a command cause UNKNOWN; ordinary later future
states do not poison preceding commands. This order check is evidence of an
unsafe candidate only and is never promoted to verified subscriber delivery.

Author tests use synthetic data only. The independent brute-force oracle
enumerates actual integer source/native/tick stamps, serializes using `struct`,
and checks that every direct formula match is in the indexed candidate set.
It includes large source stamps, integer ns boundaries and adjacent binary32
status ULPs; separate tests exercise rounding midpoints, duplicate UUID/native
states, the same image with multiple states, source resets, decode errors,
nonfinite values, source tampering and protected/exclusive output boundaries.
Synthetic tests provide no measured project coverage or experiment result.
