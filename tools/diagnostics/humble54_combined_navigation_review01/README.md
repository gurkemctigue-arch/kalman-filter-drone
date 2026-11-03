# Frozen54 person combined navigation diagnosis

This is a read-only descriptive decomposition of the original report and saved frame sidecars. It is not a new flight or re-evaluation. Original reports, terminal FAIL, window, full denominator, registered1.0m distance-RMSE threshold, safety/identity checks and unobserved values remain unchanged.

The original 752/752 physical truth samples reproduce distance RMSE **2.29643482982561 m** exactly, SSE **3965.756921582407 m^2**. Height RMSE is 0.14950812092949312 m. Valid navigation: 602/752; LOST/inactive: 150/752.

|Phase (original half-open boundaries, seconds)|n|Distance RMSE m|SSE share|
|---|---:|---:|---:|
|before_short_shutter: [17.8,29.8)|120|0.405809|0.498310%|
|short_shutter_requested_interval: [29.8,30.080000000000002)|3|0.278761|0.005878%|
|after_short_until_first_grid_lost: [30.080000000000002,34.900000000000006)|48|0.235790|0.067293%|
|lost_before_long_shutter_request: [34.900000000000006,42.800000000000004)|80|1.941930|7.607310%|
|long_shutter_requested_interval_already_lost: [42.800000000000004,45.88)|30|4.175510|13.189074%|
|after_long_open_through_reselection_until_first_grid_valid: [45.88,49.900000000000006)|40|5.802762|33.962800%|
|active_reselection_recovery_until_original_settled_suffix: [49.900000000000006,56.10000000000001)|62|5.293798|43.812732%|
|final_settled_active_suffix: [56.10000000000001,92.928)|369|0.303417|0.856604%|

All original primary-grid rows occur exactly once; partition SSE differs from sequential whole SSE by 0.0 m^2 under the recorded summation order. Exact stored floats are retained: 42.8 precedes 42.800000000000004 and is allocated to pre-long; 49.8 remains LOST; the first valid primary row is 49.900000000000006.

## Findings

- Early LOST through recovery before original settled suffix covers 212/752 samples and contributes 98.571915390% of full physical-distance SSE.
- LOST/inactive contributes 54.759183199% of full SSE. Active-only descriptive RMSE=1.726354648 m also exceeds1m because active recovery remains large; it does not replace the original full metric.
- First observed LOST34.86 precedes long shutter request42.800000000000004 by7.94s. The long-window first_lost42.804 and first_hover42.852 are first within-window observations, not global onsets.
- The whole physical-error maximum7.087985935152048m occurs51.0s after reselection, with valid estimate, before final suffix56.10000000000001.
- The short window passes. Long-window prediction unobserved remainsFalse; later safety/reselection checksTrue and low speed in that window do not demonstrate braking from moving flight because braking_from_motion_demonstrated=False.
- This decomposition associates error with observed phases; it does not isolate causality of the initial early loss or prove that a controller-only change would repair it. No trial outcome is upgraded.

## Metric and evidence limits

Physical follow distance is horizontal target-to-base_link ground-truth distance minus5m. Target KF position RMSE0.28993897417937853m on602valid samples is a separate estimator statistic; invalid/LOST rows are not zero estimation error. Physical full-window error remains measured for all752rows.

Inactive is an offline lifecycle/navigation classification. It does not itself prove exact HOVER onset or physical speed. The long-window original report independently records low speed but explicitly does not demonstrate braking from motion.

The last accepted raw observation before first LOST has acquisition 34.1 s and receipt 34.204 s; first LOST state receipt is 34.86 s. The completed [narrow telemetry review](EARLY_LOSS.md) also identifies a controller hold at 34.852 s and deterministic expected DROP windows from 34.2 through 34.7 s.

The later [recorded-stream reconciliation](early_loss_input_evidence01/actual_delivery_reconciliation.json) corroborates those six missing source keys in both research streams and diagnostics while the raw RGB and depth retain all 15 opportunities in the fixed descriptive 33.8–35.2 s window. All other nine keys occur in both research streams and diagnostics. The [separate direct visual review](early_loss_input_evidence01/visual_review.json) finds the pedestrian visible in all 15 images, including the six dropped keys. Original export, contact sheet and PNG bytes are archived alongside it. Reproduce the numerical comparison with `python -B tools/diagnostics/humble54_combined_navigation_review01/reconcile_actual_delivery.py`.

These are recorded-message presence/absence observations. A reader's latest clock is not a precise callback receipt time. This post-hoc early-loss window cannot replace the fixed four-slot short-shutter input attachment, and it does not change the original FAIL.

The [actual input-gap timeline](actual_input_gap.png) and [PDF](actual_input_gap.pdf) plot the archived source keys alongside recorded diagnostic completion times and the original source-age deadline. `actual_input_gap_plot_receipt.json` binds all three small inputs and both output bytes. Root directly inspected the PNG. `plot_actual_input_gap.py` never reads a bag or changes an evaluator.

The original terminal navigation evaluator reports RECORDED_WITH_CENSORED_FAILURES. Its top engineering negative evaluator is surface_flight. The distance-RMSE threshold exceedance is an additional diagnostic comparison against the unchanged frozen plan, not a rewritten terminal result.

Input hashes, exact event payloads, numerical reconciliation and preserved original acceptance are in phase_decomposition.json.

[Full original distance timeline](original_distance_timeline.png) and its [PDF](original_distance_timeline.pdf) retain all 752 samples and the original threshold. `plot_receipt.json` binds the input and generated output bytes. Root directly inspected the PNG; the early loss, subsequent distance growth and recovery are visible. This is a descriptive visualization, not a new flight or revised verdict.
