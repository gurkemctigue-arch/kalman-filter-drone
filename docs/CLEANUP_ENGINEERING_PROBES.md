# 正式研究结束后的两次独立退出清理验证

本文准备独立的退出清理验证，尚未执行这些真实飞行。正在进行的 v3 正式研究继续使用其冻结源码；本项必须等 166 次主飞行、166 项主离线分析、16 次扩展飞行及其 16 项补充分析全部结束后，独占执行。失败、中断和证据不完整均保留，不把“终态”解释成“通过”。这两次清理验证不计入原有研究分母。

主版运行器仅向 ROS launch 主进程发初始 SIGINT，并使用 `stdin=DEVNULL` 保证 launch 非交互转发。是否真正解决退出问题，须由下述两个图的实际逐节点证据验证，不能仅凭代码、单元测试或外层退出码判断。历史问题和信号路由依据见 [退出清理审计](POST_FREEZE_SHUTDOWN_REVISION.md)。

## v3 输入与就绪守卫

`scripts/run_cleanup_probe.py` 不再隐式使用 v2 路径。`--check-ready` 和 `--execute` 必须显式提供以下五个参数；默认无动作只打印计划，不创建结果目录或启动进程：

| 参数 | v3 值（以下命令在 WSL 中运行） |
| --- | --- |
| `--formal-results` | `/root/uav_tracking_fullplan_v3/results` |
| `--formal-plan` | `/root/uav_tracking_fullplan_v3/results/full_plan_research_v3/plan.json` |
| `--offline-manifest` | `/root/uav_tracking_fullplan_v3/results/full_plan_research_v3/offline_manifest.json` |
| `--engineering-manifest` | `/root/uav_tracking_fullplan_v3/results/extended_engineering_v3_matrix/manifest.json` |
| `--supplement-manifest` | `/root/uav_tracking_fullplan_v3/results/full_plan_supplement_v3/manifest.json` |

上述扩展和补充目录必须与实际交付命令一致；不得为了通过守卫制造 v2 别名清单。正式 results 实际解析到 D 盘 `results/frozen_fullplan_v3`，守卫接受冻结根 results 符号链接或对应的数据盘路径。所有显式输入和主计划引用的子清单必须实际位于同一个正式 results 内，主计划与主离线清单必须属于同一 study 目录。

守卫读取小型原始 JSON，不依赖网页或 summary 的完成布尔值，具体要求：

- 主计划内容摘要有效，三份飞行子清单恰好覆盖 166 个唯一名字，各槽均已终态。
- 主离线清单绑定该主计划 SHA，恰好覆盖相同 166 个名字，各槽均已终态。
- 扩展清单自己的计划 SHA 有效，16 个唯一槽与计划逐一一致且终态；源码摘要与预注册摘要和主计划一致，名字不得与主研究重叠。
- 补充清单自己的计划 SHA 有效，同时绑定准确的主计划 SHA、扩展计划 SHA、冻结根和相同 16 个试验，各槽均为 `RECORDED`、`INCOMPLETE_EVIDENCE` 或 `INTERRUPTED`。
- 每个声称 `RECORDED` 的补充槽均有两项已完成任务：`online_state_accuracy` 和 `follow_dynamics`，新执行任务的返回码须为 0。
- 补充计划保存的主计划、主离线和扩展清单源文件 SHA 与字节数必须和当前文件一致，缺失、重复、过期源绑定均拒绝。仅重算补充计划自身 SHA 无法绕过这些交叉绑定。

`--check-ready` 只验证这些账本，不认证进程空闲。真正 `--execute` 还必须在全新 `/root/uav_tracking_fullplan_cleanup_NAME` 根内运行；核对该根自己的构建、导入隔离和测试成功证据，持有旧正式研究锁与新清理根锁，并拒绝任何仍活动的 PX4、Gazebo、XRCE、ROS launch、bag record、研究/补充程序或本项目飞行节点。旧锁仅用只读描述符加锁，不改写其内容。

## 新建独立冻结根

当前 v3 飞行活跃期间不执行同步、构建、测试、冻结或清理 probe。全部研究和补充结束后，把 Windows 主版审过的清理修订同步到可变的 `/root/uav_tracking_project`，不得同步到 v3 或任何历史冻结根。相关文件为：

- `scripts/run_stage1_trial.py`、`scripts/run_cleanup_probe.py`；
- `tests/test_trial_shutdown_signals.py`、`tests/test_cleanup_probe.py`、已有 seed 测试替身兼容修订；
- 本文和退出清理审计文档。

同步后核对源文件 SHA，运行有针对性的纯夹具测试。新增 v3 清理夹具已于 2026-10-27 在 Windows Python 中通过 26 项；新 Linux 清理根仍须通过自己的构建、导入隔离及测试。仅在这些检查通过且仿真独占窗口成立后，复用现有冻结脚本：

```bash
bash /root/uav_tracking_project/scripts/freeze_full_plan_workspace.sh \
  /root/uav_tracking_fullplan_cleanup_v3 \
  /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_cleanup_v3
```

冻结脚本拒绝已有根和已有结果盘目录，在新 ext4 源码根构建 ROS 包，核对算法、节点、生成消息和 ament prefix 的实际导入路径，保存 `freeze_validation/import_isolation.json`、源码摘要、构建及全套测试日志。任一步失败均保留证据并停止，使用新名称处理后续修订，不覆盖失败根。

## 就绪检查与两条执行命令

以下仅为待执行命令。进入新根后先检查账本；通过后逐条运行两次真实 probe，等待第一次结束并完成清理再开始第二次：

```bash
cd /root/uav_tracking_fullplan_cleanup_v3

bash scripts/run_research_session.sh scripts/run_cleanup_probe.py \
  --probe stage1 --prefix cleanup_v3 --check-ready \
  --formal-results /root/uav_tracking_fullplan_v3/results \
  --formal-plan /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/plan.json \
  --offline-manifest /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/offline_manifest.json \
  --engineering-manifest /root/uav_tracking_fullplan_v3/results/extended_engineering_v3_matrix/manifest.json \
  --supplement-manifest /root/uav_tracking_fullplan_v3/results/full_plan_supplement_v3/manifest.json

bash scripts/run_research_session.sh scripts/run_cleanup_probe.py \
  --probe stage1 --prefix cleanup_v3 --execute \
  --formal-results /root/uav_tracking_fullplan_v3/results \
  --formal-plan /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/plan.json \
  --offline-manifest /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/offline_manifest.json \
  --engineering-manifest /root/uav_tracking_fullplan_v3/results/extended_engineering_v3_matrix/manifest.json \
  --supplement-manifest /root/uav_tracking_fullplan_v3/results/full_plan_supplement_v3/manifest.json

bash scripts/run_research_session.sh scripts/run_cleanup_probe.py \
  --probe stage3_multi --prefix cleanup_v3 --execute \
  --formal-results /root/uav_tracking_fullplan_v3/results \
  --formal-plan /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/plan.json \
  --offline-manifest /root/uav_tracking_fullplan_v3/results/full_plan_research_v3/offline_manifest.json \
  --engineering-manifest /root/uav_tracking_fullplan_v3/results/extended_engineering_v3_matrix/manifest.json \
  --supplement-manifest /root/uav_tracking_fullplan_v3/results/full_plan_supplement_v3/manifest.json
```

若目录已存在，不复用或覆盖；为新修订另选 cleanup 名称和 prefix。试验目录分别为 `cleanup_v3_stage1_person_seed00`、`cleanup_v3_stage3_multi_person_seed00`，各有相邻的 `_cleanup_audit/`。默认打印计划可在 Windows 中执行，但研究运行期间不需要额外执行。

公共 ROS 可执行节点为 `parameter_bridge`、`px4_adapter`、`flight_tf`、`detector`、`state_estimator`、`controller`、`flight_supervisor`。阶段一加 `scenario_motion`，恰好 8 个；阶段三 multi 加 `stage2_motion` 与 `gimbal_adapter`，禁用 `scenario_motion`，恰好 9 个。两条 probe 使用行人 YOLO11n、320 图像、2 线程、RTF 0.5、seed 0、自适应 KF、速度控制、FOLLOW 45 秒和短长遮挡/显式重选；阶段三启用多目标和主动三轴云台。不为改变退出结果调整滤波器或控制参数。

## 证据与判断

脚本使用真实 trial runner，只在该模块中安装观察代理，不替换全局 os/subprocess。`process_events.jsonl` 逐事件刷新，保存真实 Popen、初始信号、等待与超时路径，包含 UTC、单调时间、PID/PGID/SID、启动 tick、信号目标和退出码；发信号前记录实际后代，结束后检查原 PID/启动 tick、session 和相关进程残留。

`cleanup_report.json` 保留外层退出码、逐 ROS 节点启动和退出记录、错误日志、fallback、残留、受保护小清单前后 SHA、probe 源码及证据 SHA。只有准确的 8/9 节点均在停止标记后明确 clean、没有缺失/重复记录或 traceback、没有 ROS 超时升级、没有观测到残留且源码/旧清单不变，才能判 `PASS`。外层 `ros=0`、monitor=0 或飞行验收 PASS 均不能替代逐节点清理证据。第一次若有残留，第二次须拒绝；保留 FAIL 并单独诊断，不能以批量 kill 掩盖。

本工具不读取或解压 bag，也不重评检测、身份和跟随精度；原 runner 仍录制该次 bag 和视频。浅层崩溃检查只比较新根、试验目录、PX4 rootfs 和 `/var/crash` 顶层 `core*`/`.crash` 文件元数据，并保留实际 `core_pattern`。WSL crash handler 的其他输出位置不在范围内，不能据此声称全系统无 core。

纯夹具的待执行命令为 `python -m unittest discover -s tests -p test_cleanup_probe.py -v`。最终状态以新结果目录真实 `cleanup_report.json` 为准；准备脚本、编写夹具和列出命令均不代表两次 probe 已完成。
