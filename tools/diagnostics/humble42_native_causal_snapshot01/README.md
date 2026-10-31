# Humble42 native causal-window export

This snapshot preserves the reviewed extractor, synthetic review, exact invocation
and root's actual Ubuntu 22.04 / Humble execution receipts. Original slot09
remains FAIL; the original core batch remains 8 PASS / 1 FAIL / 3 PENDING.

On 2026-10-31 at 20:54–20:57 UTC the extractor completed one full native traversal
of 204,788 messages. It reproduced all original topic counts and exported the
29.5–33.0-second source window plus explicitly labelled boundary/context records.
RGB, depth and CameraInfo at exactly 31.4, 31.5, 31.6, 31.7 and 32.2 seconds were
all present once. Original pixels, encoding, stride, endianness and CDR are retained
in the local external archive. No nearest-frame substitution was used.

Native traversal and two compressed-payload hash passes took 177.974 wall seconds
in total. The original inputs and payloads remained unchanged. The borrowed native
reader has no exposed close API; its references were released and the owned
temporary cache was removed, with tempfile configuration restored. The actual
manifest SHA is `085ac699eafd5fb750328a00626d0bd144cd002b10a1d433fb5e5adaf8d78dfb`.

The 42 synthetic review cases, metadata preflight and actual export cover different
scopes. This is raw evidence export. It performs no inference, association replay,
simulation, new scoring or original-verdict repair. Private filter priors and
unrecorded pairwise rejection scores remain unobserved. Recorder nanoseconds and
the preceding recorded `/clock` proxy remain separate from source timestamps;
the proxy is not an exact callback-receive timestamp.

See `actual_export_summary01.json` for local source bindings and execution limits.
The complete 65MB derivative event stream, raw images, CDR and full manifest remain
at `D:/WSL/UAVHumble22-validation/humble42_native_causal_window01/`.
