# Current fixed07 / actual short03 outcome

The current reviewed source candidate is source_sha256_windows07.json, SHA `4cbc8ad3a2fb04c25599b8df90cf66ff84f1aa7ff17d5b3965bfc96d1be04730`. Validation receipt SHA: `f1c8c72b05209afc376eb4b23b4a65e22cb3280955566f071b347d5f03aff54f`. Root review precedes the next native bench. No new bench was started by this change.

Actual short03 finished normally: all five algorithm/replay workers exited 0 and cleanup completed, but its result is NOT_OBSERVED, with 0 candidates and 504 UNKNOWN command opportunities. The three DDS edges retained 76/454/504 UNKNOWN takes. Those original results remain unchanged. Its original summary SHA is `d893695df5ef0eabc764970aa31b2afdf410cbc65763211ca37baee77f8e0037`.

The real lightweight Humble probe confirmed exact root modules/slots and the unsupported IDL declaration `boolean`. Fixed07 adds that spelling while preserving strict Python bool checks, declared type strings, all fields, bit widths and unknown rejection. A separately authorized real CDR compatibility check passed for all three actual root types, including one real nested TargetObservation; the private c7 typed compatibility cases also passed with synthetic DDS windows. This checks schema compatibility, not actual DDS edges or pipeline latency. See CHANGE_FIXED07.md, schema_probe07_native.json and schema_verify07_native.json. Windows tests: 25/25 PASS.

Use a fresh output directory for any subsequent bench, e.g. `/root/humble54_pipeline_bench01_short04`; do not rerun into short01/02/03. The original short input manifest remains unchanged. Root controls actual execution after its own review. The Humble environment requirements below still apply. No uninstrumented baseline exists, and historical strict UNKNOWN / physical E2E conclusions do not change.

## Earlier entry text retained for history

# 当前可审查版本

当前运行源码以 `source_sha256_windows06.json` 为准，清单原字节 SHA 为 `4c5bdb715448ea597405b41e2cb1d21c4fa7befec8d5a0a27e84f321b87f1226`。fixed05 修复新 JSON 发布竞态，fixed06 补齐动态导入前的模块注册。23项作者测试通过，root核对当前源码清单并独立通过新增的 dataclass 动态加载回归；此前也已独立通过两项真实文件系统并发回归。修复和旧实现失败负对照见对应 CHANGE、validation 与 negative_control 文件。

fixed04 的首次原生短回放因就绪文件发布竞态停止；fixed05 的第二次短回放四节点均已就绪，随后在读包模块动态导入时停止。两次有效计时样本均为0，全部子进程已退出；原输出 `/root/humble54_pipeline_bench01_short01` 和 `short02` 保留。旧源码和清单分别逐字节归档在 `archive_fixed04/` 与 `archive_fixed05/`。fixed06 的下一次原生输出使用新的 `/root/humble54_pipeline_bench01_short03`，实际执行结论以新 summary 为准。

`validation_windows06.json` 和 `test_windows06.log` 是当前版实际的 Windows 测试记录。01—05 文件保留历史摘要，不能用它们的源码摘要校验当前源码。README 末尾对01的引用属于初次准备说明；当前以本页和06清单为准。

基础管线通过了20项作者测试、独立破坏归因及端点隔离检查，fixed06合计23项。当前有效软件时延样本仍为零。原生短回放须在其他重任务完全退出后显式执行；原命令自行持有项目锁，无需外层另加 flock。旧04独审保留在相邻的 `../humble54_pipeline_timing_review01/independent_review01.json`，按其对应版本阅读。

原调用一次和对象保持的检查不证明没有开销。钩子包含取消息时的 Python profile、字段快照、JSON 编码、锁及队列操作；所得时延只描述被观察的独立软件回放。历史 strict UNKNOWN 和物理 E2E 结论均不变。未来实际运行状态以本次新输出目录中的原始日志和 summary 为准。

`full_replay_manifests01/` 已补充行人、汽车各一份完整原速回放清单，并独立核对原小文件绑定，均未实际运行。完整清单不设置记录数截断，各含 50,117 条所选输入机会；全包原记录跨度约 752.5 秒。现有 900 秒上限名义上可容纳，但启动、模型加载、解压和调度耗时尚未实测，不能保证成功。先通过原生短回放、确认实际 FOLLOW 来源链和清理，再决定完整回放。

README 的原生命令假定已经进入本项目的 Humble 环境。从 Windows 新启动的非交互 WSL shell 必须先显式加载同一冻结环境，再执行该命令：

```bash
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble54
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export PYTHONDONTWRITEBYTECODE=1
source /root/uav_tracking_fullplan_v4_humble54/scripts/humble22_env.sh
```

该环境提供原 Python venv、Humble、px4_msgs、ros_gz 及已登记 DDS 设置。台架随后在实际进程中选择独立的 domain 211，不启动 SITL 或 Gazebo。不得依赖 Windows 启动的其他 shell 自动继承这些变量。
