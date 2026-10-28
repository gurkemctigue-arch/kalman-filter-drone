# 原计划扩展条件的 16 项工程验证

2026-10-28 交付更新：正式 `v3` 主研究 166/166 槽、独立工程扩展 16/16 槽及相应离线与补充台账均已终态；扩展原始结果为 2 PASS、14 FAIL。最新交付状态见 [三阶段交付状态](DELIVERY_STATUS.md)。终态不表示全部验收通过，失败和证据不完整继续保留。

## 历史协议与执行快照

以下保留协议制定时的 `v2` 状态、参数和执行约束，文中的“正在运行”“尚未开始”等描述是历史快照，不代表 2026-10-28 的交付进度。

`v2` 已完成冻结，四个 ROS 包构建、导入路径隔离和冻结 Linux 环境 492 项测试全部通过。主研究 166 个槽位已生成，首批 8 次正式飞行正在运行；独立离线阶段和本文件的额外 16 项工程扩展尚未开始。扩展工程使用独立 `extended_engineering_v2` 前缀和清单，不并入主 166 分母；以下为后续操作说明，当前不得与主研究并行启动。实际进度以各自动态清单为准，冻结 SHA 及主研究状态见 [研究运行说明](FULL_PLAN_RESEARCH_RUNBOOK.md)。

旧 `v1` 的 8 次正式尝试按原评价仍为 7 PASS、1 FAIL，原录制、报告与失败全部保留，不进入 v2 分母。评价修订 3 已对原汽车 raw bag 独立核对为 PASS，报告与 SHA 审计另存；原始 FAIL 和修订 2 FAIL 均保留，详见 [评价修订 3](EVALUATION_REVISION_3.md)。

`scripts/run_extended_engineering.py` 对主研究 166 项之外的原计划条件建立独立清单，并串行调用真实 `run_stage1_trial.py` 和 schema 3 飞行评价器。`--plan-only` 不启动仿真；单元测试中的替身运行不属于飞行成果。

| 条件 | 类别与模式 | 项数 |
| --- | --- | ---: |
| 已预注册的 `speed_changes` 加减速 | person/car × velocity/position | 4 |
| 在线深度噪声、深度空洞、检测丢帧、通信延迟及组合故障 | person/car × 5 种故障，velocity | 10 |
| 更远的期望水平距离 | person 7 m、car 12 m，velocity | 2 |

全部采用 adaptive KF，每个条件仅 seed 0 的一次独立飞行，目标名义速度按该 seed 固定生成；每次在进入 FOLLOW 后继续 45 秒，包含真实渲染的短/长遮挡及丢失后的显式重新选框。这个清单不增加主研究的 166 分母，不能称为每种故障、距离或运动条件各十次独立重复。已有 clean/标准距离研究保持独立统计。

资源直接读取 `planning/online_estimator_preregistration.json`，没有另行调小检测器或放宽安全年龄的命令行选项。当前预注册为请求 RTF 0.5，行人 YOLO11n/320/2 线程、汽车 YOLO11s/640/4 线程；请求 RTF、权重、线程、条件和轨迹参数写入每个计划槽位。`v2` 已核对并冻结这些资源，用于保留本机渲染和推理期间的仿真时间新鲜度；它不证明真实墙钟实时能力。旧 `v1` 冻结记录、此前 0.7 资源探测、失败和评价版本均保留。

以下命令于已冻结的 `/root/uav_tracking_fullplan_v2` 工作区执行，其 `results` 已链接到 D 盘的 `results/frozen_fullplan_v2`。须等待主研究飞行和离线任务均退出，再安排扩展工程的独占运行窗口：

```bash
bash scripts/ros_python.sh scripts/run_extended_engineering.py \
  --prefix extended_engineering_v2 \
  --output results/extended_engineering_v2_matrix --plan-only

bash scripts/ros_python.sh scripts/run_extended_engineering.py \
  --prefix extended_engineering_v2 \
  --output results/extended_engineering_v2_matrix --resume --stop-after 1

bash scripts/ros_python.sh scripts/run_extended_engineering.py \
  --prefix extended_engineering_v2 \
  --output results/extended_engineering_v2_matrix --resume
```

首次运行在任何飞行之前写入全部 16 个 PENDING 槽位、预注册文件哈希以及运行代码、配置、场景、资产、权重的源哈希。续跑重新核对冻结配置和代码；有变化须新建 prefix/output，不能把改过的配置混进旧清单。编排器共用 `run_full_plan_research.py` 的工作区进程锁，防止通过这两个编排器同时启动仿真；不应另行手工启动共享 PX4、Gazebo 或 ROS domain 的飞行。

每次飞行退出并完成进程清理后，先调用与主研究相同的 `uav_tracking.research_failures.classify_infrastructure_failure` 核查基础设施资格；通过后运行该次离线评价。评价完成后再次检查，防止 metadata 完整但核心时钟或无人机消息实际不可解码的试验继续消耗后续槽位。检查仅读取轻量记录，不解压或打开 bag 数据库。评价明确传入该槽位真实的 `desired_distance_m` 和高度；远距离试验不得仍按 person 5 m/car 9 m 计算误差。仅接受 schema 3、类别/距离/高度与飞行一致、无起止裁剪的报告。完整短/长遮挡、悬停与重选验证沿用该评价器，不因扩展条件放宽。

任一次检查确认基础设施失败，当前槽保留 FAIL，立即停止本次调用，余下槽保持 PENDING。飞行后即失败时，评价记为基础设施证据缺失并跳过；评价后才暴露的问题保留已生成报告及其返回码。缺少必需录包或核心消息、明确的 supervisor ABORTED、核心进程崩溃，以及有足够观测支持的未起飞属于早停范围；普通歧义、目标丢失、跟踪/精度 FAIL 或单独非零 monitor 返回码不触发基础设施早停。每次检查及证据保存在槽内 `infrastructure_checks`，当前资格结论存于 `infrastructure_failure`。

清单保留各命令参数、开始/结束时间、返回码、独占创建的日志及报告哈希。普通飞行失败且部分 rosbag 的基础设施资格通过时仍执行评价并继续下一槽；飞行失败不能被离线 PASS 覆盖。已有试验目录、旧版本报告、缺少 bag 或评价配置错误均记 FAIL，不覆盖或自动收编现成目录。续跑只执行 PENDING；遗留运行中状态改为 INTERRUPTED；失败和中断不自动重试。基础设施早停后先诊断环境，再显式续跑未执行槽位；更正后需要另建版本的配置仍须新建 prefix/output 并保留旧结果。

输出为 `manifest.json`、`summary.json` 与每槽位命令日志；触发基础设施早停时追加 `infrastructure_stops.json`，记录计划哈希、试验名、`after_flight` 或 `after_evaluation` 检查阶段及证据，不覆盖已有停止历史。实际飞行的 rosbag、视频、配置及 `offline_evaluation.json` 位于各自 `results/TRIAL/`。尚未运行的槽位始终 PENDING。

14 项扩展编排离线回归覆盖真实 CLI 的资源/故障/轨迹/距离传递、串行顺序、16 项完整分母、合格部分 bag 的失败评价、覆盖拒绝、强中断保存、冻结漂移及 plan-only 不飞行。新增回归使用真实轻量文件触发缺包、ABORTED、进程崩溃、未起飞和评价器核心消息解码失败，验证当前 FAIL、其余 PENDING、停止历史追加及失败名字不自动重试；并以普通跟踪 FAIL 验证继续下一槽。它们不是实际飞行结果。
