# WSL Gazebo RGB-D shutdown diagnosis

The Humble04 car trial ended with Gazebo `-11`. This remains a core process
crash, including when the flight monitor and recording completed successfully.
The frozen trial and its failure classification are unchanged.

The corresponding ELF core places the main thread in
`SignalHandlerPrivate::OnSignal -> SensorsPrivate::Stop -> std::thread::join`.
The render thread had reached `__nptl_deallocate_tsd` and called an invalid TLS
destructor. Gazebo's backward signal handler then crashed in
`_Unwind_Backtrace`, which explains why the normal log contained no useful
backtrace. Disabling that handler would hide the second fault without repairing
the first.

A new isolated probe preserved the same PID's mappings before shutdown. Its
original callback IP `0x7f6ddc87eb10` maps to
`/usr/lib/wsl/lib/libd3d12core.so`, ELF offset `0x2edb10`, which was no longer
mapped at the fault. The default EGL command had loaded WSL D3D12 through Mesa;
the historical `egl` option therefore did **not** establish CPU rendering.

Each probe used the frozen Humble04 car world, real nonempty 640×480 RGB and
depth frames with increasing acquisition stamps, LP_NUM_THREADS=4 and
OMP_NUM_THREADS=2. No ROS graph, PX4, YOLO or bag reader ran. Every probe used
its own random `GZ_PARTITION` and process group; failures were retained.

| Rendering / shutdown change | Repeats | Observed result |
| --- | ---: | --- |
| Original EGL driver selection, SIGINT | 2 | Both `-11` |
| Original EGL, `/server_control stop: true` | 2 | Both ACK true, then `-11` |
| Preload only `swrast_dri.so`, server stop | 2 | Both ACK true, then `-11` |
| Preload only WSL `libd3d12core.so`, server stop | 2 | One exit 0; one timeout requiring owned-process cleanup |
| Explicit llvmpipe, server stop | 1 | Actual RGB-D, exit 0, no residual group |
| Explicit llvmpipe, SIGINT | 1 | Actual RGB-D, exit 0, no residual group |

The upstream service was verified in gz-sim 8.15 commit
`446a44335a45b704b4d36dabcc5508ee34eeb3d8`, `ServerPrivate.cc:386,416` and the
installed msgs10 `server_control.proto`. It is `/server_control`, accepting
`gz.msgs.ServerControl` with `stop = 6`; the response is `gz.msgs.Boolean`.
An ACK starts an asynchronous stop thread and does not prove clean exit. Since
this change alone failed, the flight runner retains its existing SIGINT stop.

The selected compatibility option is explicit CPU rendering, scoped to the
Gazebo shell branch:

```bash
python3 scripts/run_stage1_trial.py ... \
  --render-backend egl --gazebo-render-driver llvmpipe
```

This sets `LIBGL_ALWAYS_SOFTWARE=1`, `MESA_LOADER_DRIVER_OVERRIDE=swrast` and
`GALLIUM_DRIVER=llvmpipe` only for Gazebo. The option defaults to `auto` to retain
the meaning of old commands. ROS/PX4/YOLO environment and system libraries are
not modified. No preload workaround is enabled in the flight runner.

After unpause, `configuration/gazebo_rendering_libraries.json` records the
owned process's selected environment, actual ELF mappings, SHA256, inode and
device. The CPU contract requires actual `swrast_dri.so` and LLVM mappings and
rejects D3D12 or WSL GPU-driver mappings. Missing initialization or mismatched
library provenance fails the run. Environment declarations alone cannot pass.

The two successful CPU probes took about 5.58 and 5.34 wall seconds, including
startup and a minimum five-second warmup. This is a shutdown validation, not a
full-flight inference or control performance result. New person/car development
flights must measure performance before formal registration.

The small raw probe reports and logs are stored under the local ignored
`results/gazebo_shutdown_smokes/`; originals are in
`/root/uav_gazebo_shutdown_smokes/` in `UAVHumble22`. The probe is reproducible
with `scripts/probe_gazebo_shutdown.py`. Cores are kept separately from Git.

The ROS shutdown observation is independent. A Humble subscription take raised
the exact pybind conversion RuntimeError after SIGINT. The supervisor now
recognizes it only when the context explicitly reports closed and its traceback
contains `rclpy.executors._take_subscription`. Other errors, live contexts and
unknown context state still raise. ROS child failures remain separately audited
even if `ros2 launch` itself exits 0.
