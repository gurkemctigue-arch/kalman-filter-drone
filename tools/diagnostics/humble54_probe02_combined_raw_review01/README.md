# Closed person combined raw-window review

`original_export/` preserves the completed native export for simulation acquisition times 33.8–35.2 s: its manifest, all 15 original RGB PNGs, and the contact sheet. `source_rules/` preserves the SHA-matched fault-bridge source, recorded fault parameters, and source map. All 20 archived files are byte-identical copies, with source paths and hashes recorded in `actual_review.json`; original results are retained.

The reviewer checked every PNG hash, decoded all images, viewed the contact sheet and each original 640×480 image, and observed a visible person in every frame. Each acquisition had raw RGB and depth. The six 34.2–34.7 s acquisitions lacked research RGB/depth and diagnostic records, exactly matching the recorded seed 4, fraction 0.1 drop rule. The other nine acquisitions had all five streams and recorded one candidate with valid depth.

This review evaluated only the SHA-matched pure `frame_dropped` function. It started no bridge, ROS, WSL, model inference, bag read, or telemetry scan. Raw visibility and diagnostic candidates do not establish track/KF acceptance or physical identity. The historical engineering result remains FAIL. `actual_review.json` preserves the scope and unknowns at this review step; later telemetry evidence is linked from the planning review rather than rewriting this original artifact.

[Original-pixel contact sheet](original_export/contact_sheet.png) · [Actual review](actual_review.json) · [Planning review](../../../planning/reliability-v4-probe02-combined-review-20261103.md)
