# Early loss: narrow evidence and limits

The original combined trial loses the selected target before the long shutter. Its full result remains FAIL and its whole752-sample distanceRMSE remains2.29643482982561m against the original1.0m maximum. No original report or threshold changed.

The exact fault source SHA256 is c07b1b5e7a7addbe2b7b4ad63cb798503646a8f92cf14aa66a1fd35582a486f0, matching both original plan and recorded runtime source manifest. With recorded seed 4 and drop_fraction 0.1, the original SHA256(seed:200ms-window) rule expects KEEP at 34.1 s, DROP from 34.2 through 34.7 s (windows 171 through 173), and KEEP at 34.8 s. These are deterministic injection expectations, not observed input deliveries.

Original telemetry independently records:

|Event|Source / operational seconds|Evidence|
|---|---|---|
|Last accepted observation|acquisition34.1,output34.204|confidence0.850835; valid depth; valid ground fit; accepted; selectedtrack1; no rejection|
|Controller safety hold|34.852000000000004|stale_target; source measurement_age0.7520000338554382; lifecycle4|
|Track LOST|34.86|last_measurement34.1; source age0.76; rejected_measurements0; no ambiguity|
|Next processed detection|acquisition34.8,output34.904|sourcegap0.7; confidence0.830464; validdepth; completebbox|
|Return is after LOST|34.904|track1 staysLOST; newtrack2; no_accepted_selected_measurement for selected target|

The original sourcegap0.7s plus observed source-to-output delay0.104s yields previous measurement source age0.804s at return, exceeding the unchanged0.75s protection. This accounts for the observed safety transition without requiring a depth/geometry/gating failure. The unchanged0.60s max_observation_age and0.75s prediction protections are retained.

Actual native/research RGB-D message payloads for these six frames have not been read. A processed-diagnostic gap does not establish input absence. The injection schedule and boundary timing match; final actual input-delivery corroboration still requires the original message stream in an idle analysis window. ros.log added no source-aligned input-delivery evidence in this review, and sensor_faults.log is empty; no inference of absence is drawn from those logs.

The original long shutter starts42.800000000000004, about7.94s after firstLOST. Its within-window42.804 LOST and42.852 HOVER observations cannot be interpreted as global onsets. The trial's later safety/no-switch/reselection success does not turn its earlier tracking loss, absent long-window prediction, or full task distance failure into a pass.

The phase decomposition is in phase_decomposition.json. Source hashes, deterministic windows, exact compact telemetry events, limitations and preserved original verdicts are in early_loss_evidence.json. early_loss_telemetry_window.json contains603selected scalar-focused rows with original line numbers; covariance/position matrices are deliberately omitted.
