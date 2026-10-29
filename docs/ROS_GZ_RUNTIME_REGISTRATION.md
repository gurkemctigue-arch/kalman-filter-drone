# 独立 ros_gz 运行环境登记

`scripts/ros_gz_runtime.py` 只运行 Git、ldd 和文件/proc 读取，不启动 ROS、Gazebo 或 PX4。生产探测仅支持 Linux；跨平台单元测试使用显式 `ORCHESTRATION_FIXTURE_ONLY` 后端，生产验证拒绝此类证据。

登记文件是 `CANDIDATE_REQUIRES_INDEPENDENT_REVIEW`，须由外部 review/guard 绑定其文件 SHA。`verify` 的 PASS 仅表示源文件和 ELF 与该候选一致；桥接功能、正常析构、试验验收分别提供证据。

```bash
python scripts/ros_gz_runtime.py register \
  --overlay-root /root/uav_humble22/ros_gz_shutdown_A01_ws \
  --repo-root /root/uav_humble22/ros_gz_shutdown_A01_ws/src/ros_gz \
  --expected-commit 856e319ee4da713609b3f6e58c74ac8db7662482 \
  --patch /path/to/final-root/patches/ros_gz_bridge_ownership_shutdown_A01.patch \
  --plugin-elf /root/uav_humble22/ros_gz_ws/install/ros_gz_interfaces/lib/libros_gz_interfaces__rosidl_typesupport_fastrtps_cpp.so \
  --output /path/to/final-root/config/ros_gz_runtime_humble22.json
```

overlay 根是含 `install` 的工作区，支持 isolated 和 merge install，拒绝同时出现两个 `parameter_bridge`。登记锁定 Git commit、工作树和暂存 diff、索引状态、submodule 状态，以及显式 patch 的 SHA；有 tracked diff 时必须提供 patch，不接受未审核的 untracked 文件或 assume-unchanged/skip-worktree 索引。它锁定可执行 ELF、`libros_gz_bridge`、显式 `--plugin-elf` 插件本体，以及桥与各插件 ldd 闭包的路径/SHA 并集。插件参数可重复，运行时须实际映射全部登记插件，未知 ros_gz 库不能按 basename 放行。桥可执行文件及 bridge 库必须来自所选 overlay；明确登记的原 `ros_gz_interfaces` underlay 可保留。每个文件保留 1 GiB 资源上限，使用 1 MiB 流式哈希，容纳实际约 538 MB 的 RelWithDebInfo 库。登记同时记录源码与二进制，不自行证明二进制可从源码重建；实际构建回执也应进入独立 review。

```bash
python scripts/ros_gz_runtime.py verify \
  --registration /path/to/final-root/config/ros_gz_runtime_humble22.json \
  --expected-registration-sha256 <independent-review-sha256> \
  --patch /path/to/final-root/patches/ros_gz_bridge_ownership_shutdown_A01.patch \
  --pid <owned-parameter-bridge-pid> --pid-start-ticks <launch-start-ticks> \
  --output /path/to/new-receipt.json
```

`--pid` 可省略，此时只检查现时源码、patch、依赖解析和 ELF。指定 PID 后，还检查前后内核创建时间、`/proc/PID/exe`、每个登记 ELF 的实际 maps、device/inode、文件 SHA；缺失、deleted、额外旧 ros_gz 映射或身份变化均失败。调用方负责证明 PID 属于自己的 launch 子树。这是一次观察，不承诺后续进程持续健康。

`--patch` 在 verify 中允许使用冻结副本，SHA 和大小必须与原登记完全相同，回执保存实际核验路径。它允许离开原主树 patch 路径；源码 repo 和 overlay 不迁移。输出文件始终使用独占创建，拒绝覆盖旧登记或回执。

Python 接口为 `create_registration(overlay_root, repo_root, patch_path=..., expected_commit=...)`、`verify_registration(registration, patch_path=...)` 和 `verify_live_process(registration, pid, expected_start_ticks=..., patch_path=...)`。最小集成是在外部 guard 先核登记文件 SHA，再调用现时验证；飞行在 physics 仍暂停时验证真实 owned bridge PID 并存独立实际映射回执。原 PX4 和 Gazebo 磁场注册保持各自用途。

`run_stage1_trial.py` 支持 `--ros-gz-runtime-registration`，未显式指定时仅在 final-root 存在 `config/ros_gz_runtime_humble22.json` 才启用。进程启动前验证源文件和 ELF，并按原字节保存 `configuration/ros_gz_runtime_registration.json`，另存 `ros_gz_runtime_preflight.json`；已登记 patch 必须有 final-root 中的同字节副本。

启动 ROS launch 后，在 graph readiness 和解除 physics 暂停前，仅沿该 launch 的内核子进程列表查找唯一 `parameter_bridge`，核对父子关系与创建身份。查找上限为 64 个进程、512 个线程；在同一个最多 5 秒的窗口内，固定首次发现的 owned PID/链，等待已登记 ELF 的真实路径全部映射，之后仅执行一次完整 ELF 校验，并复核 ownership。完整 ELF 校验另计。初始化期间尚未映射的插件可等待；错误 executable、deleted 或未登记 ros_gz 映射立即失败。成功回执 `ros_gz_runtime_actual.json` 包含 `registration_file_sha256`、`owned_launch` 的 leader/process/ancestor_chain，以及模块的 `mapped_elfs`。无关进程、多个 bridge、身份变化或缺失映射超时均不能放行；失败保留 `ros_gz_runtime_actual_error.json`。

退出后再次核对配置文件 SHA、源代码和 ELF，并要求 ROS launch 退出码为 0 且日志没有 `process has died`，保存 `ros_gz_runtime_after.json`，失败则保存 `ros_gz_runtime_after_error.json`。此项失败先等待 recording 归档完成，再作为试验错误抛出；已有飞行异常继续保留。上述三份校验回执必须绑定同一登记文件 SHA，外部 clean/formal 验收仍负责审核该 SHA 与独立构建、功能和退出证据。

```powershell
python -m unittest tests.test_ros_gz_runtime -v
python -m unittest tests.test_ros_gz_trial_hooks tests.test_trial_shutdown_signals -v
```

测试使用极小临时 Git 仓库和 ELF/proc fixtures，不运行真实 ldd、ROS、WSL 或仿真；真实 Linux 登记、桥功能与退出测试由独立现场流程完成。
