# Humble41 read-only canonical core12 progress bridge

Reads only the original plan, started markers and slot terminal JSON. The denominator stays 12 for ordered class/group seed004 slots. It preserves existing outcome labels, reads no bag or telemetry, computes no engineering verdict and starts no experiment.

Inert describe:

```text
python -B D:/WSL/UAVHumble22-validation/bridge_humble41_events01.py describe
```

After the independent root producer starts, replace only the two uppercase PID/token placeholders below with its actual Windows PID and creation token from the unchanged pinned monitor helper. The original plan path and file SHA are already bound. A WSL-internal PID cannot replace that Windows identity.

```text
python -B D:/WSL/UAVHumble22-validation/bridge_humble41_events01.py watch --project-root "D:/基于yolo和卡尔曼滤波" --kind core --plan "D:/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_humble41/reliability_v4_humble41_probe01_seed004_matrix/plan.json" --plan-sha256 38aa57fddd8476fd124554775fb70f63dcc0af893a9fbb914f6439a89d9a614b --pid ACTUAL_WINDOWS_PRODUCER_PID --expected-start-token "ACTUAL_WINDOWS_CREATION_TOKEN" --output D:/WSL/UAVHumble22-validation/humble41_core_events01 --interval 5
```

The output directory must be fresh and directly beneath the external validation directory. PID reuse refuses. PID exit triggers a final source scan and never supplies a missing slot or PASS. Four original completed attempts followed by an infrastructure stop still leave eight unattempted slots out of twelve.

This delivery prepared code and pure fixtures only; no real bridge, monitor or flight was started.
