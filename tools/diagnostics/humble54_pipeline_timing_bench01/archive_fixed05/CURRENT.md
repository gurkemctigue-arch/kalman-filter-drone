# 当前可审查版本

当前运行源码以 `source_sha256_windows05.json` 为准，清单原字节 SHA 为 `ae2a480453c6f69b8e544f6e4606653d48d294913bbdc155848b7c78a5af97f7`。fixed05 只修复新 JSON 发布竞态；22项作者测试通过，root另行复核全部8份源码绑定并通过2项真实文件系统并发回归。修复及旧实现失败负对照见 `CHANGE_FIXED05.md` 与 `validation_windows05.json`。

fixed04 的首次原生短回放已实际停止：就绪文件可能在写完前被读取，原 summary 为 JSONDecodeError，有效计时样本为0，全部子进程已退出。原输出 `/root/humble54_pipeline_bench01_short01` 保留，旧源码和清单逐字节归档在 `archive_fixed04/`。fixed05 的下一次原生输出使用新的 `/root/humble54_pipeline_bench01_short02`，实际执行结论以新 summary 为准。

`validation_windows05.json` 和 `test_windows05.log` 是当前版实际的 Windows 测试记录。01—04 文件保留准备过程和原失败前的历史摘要，不能用它们的源码摘要校验当前源码。README 末尾对 01 的引用属于初次准备说明；当前以本页和05清单为准。

基础管线通过了20项作者测试、独立破坏归因及端点隔离检查，fixed05合计22项。当前有效软件时延样本仍为零。原生短回放须在其他重任务完全退出后显式执行；原命令自行持有项目锁，无需外层另加 flock。旧04独审保留在相邻的 `../humble54_pipeline_timing_review01/independent_review01.json`，不冒充05的运行结果。

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
