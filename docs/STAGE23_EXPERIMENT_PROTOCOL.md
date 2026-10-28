# 阶段二、三真实闭环批量实验协议

本协议由 `scripts/run_stage23_matrix.py` 预注册，所有结果来自实际 RGB-D/YOLO/ROS/PX4/Gazebo 闭环。`--plan-only` 仅建立清单，测试中的替身进程不计入实验结果。

默认完整清单为 66 次飞行：

| 阶段与用途 | 条件 | 次数 |
| --- | --- | --- |
| 阶段二重复研究 | 行人、汽车；指定个体；crossing；seed 0–9 | 20 |
| 阶段二工程安全 | 行人、汽车；parallel、ambiguity、auto_unique 多实例；seed 0 | 6 |
| 阶段三配对研究 | 行人、汽车；midpoint 与 active；seed 0–9 | 40 |

同一 seed 的目标速度始终由 `random.Random(seed).uniform(0.45, 0.55)` 产生。同一阶段三配对使用完全相同的类别、速度、轨迹、控制模式、控制参数、故障条件和遮挡时序，仅改变云台模式。两种模式均开启真实遮挡和长失后的显式重新框选。

控制模式固定为 velocity，估计器固定为 adaptive_kf，clean 传感器条件，期望水平距离为行人 5 m、汽车 9 m；相对目标高度 2 m、起飞高度 3 m。指定个体试验必须观察到至少 3 个候选框后，按初始图像中候选框的水平中心排序，选择 middle 框；这个测试脚本规则只读取视觉检测框，不读取 Gazebo 实体名或真值身份。试验 runner 会保留每次实际参数、源代码与权重哈希、rosbag、视频和进程退出码。批量运行期间不要更改算法或参数；需要改动时创建新 prefix 和新输出目录，保留旧清单。

资源协议默认固定为仿真实时系数 1.0、行人推理图像 320/2 个 CPU 线程、汽车推理图像 480/2 个 CPU 线程。可在创建清单时通过 `--real-time-factor`、`--car-image-size`、`--car-threads` 明确修改；所有值进入冻结协议和各试验配置，续跑不可更改。同一阶段三配对始终使用相同资源，禁止只给主动云台更大的计算预算。仿真实时系数只改变墙钟推进速率，不改变按仿真时间定义的目标速度和遮挡时序。

资源探测后拟采用的正式配置为 `--real-time-factor 0.7 --car-image-size 640 --car-threads 4`，行人维持 320/2。必须在首次创建清单及每次续跑时显式提供相同参数；这里的协议说明不能代替实际 manifest 的冻结值。代码默认值保持不变，以免已有命令的含义悄然变化。

## 启动与续跑

在已安装 ROS 和项目消息的 Linux 环境中执行：

```bash
bash scripts/ros_python.sh scripts/run_stage23_matrix.py \
  --prefix stage23_research_v1 --output results/stage23_matrix_v1 --plan-only

bash scripts/ros_python.sh scripts/run_stage23_matrix.py \
  --prefix stage23_research_v1 --output results/stage23_matrix_v1 --resume --stop-after 1

bash scripts/ros_python.sh scripts/run_stage23_matrix.py \
  --prefix stage23_research_v1 --output results/stage23_matrix_v1 --resume
```

`--only-stage 2|3`、`--only-class person|car`、`--only-scenario crossing|parallel|ambiguity|auto_unique|gimbal` 只限制本次执行哪些待运行项目，不删除其余计划，不改变冻结协议哈希。`--stop-after N` 指本次最多新执行 N 次飞行；默认 0 为执行全部待运行项目。所有 66 个项目在第一次飞行之前即写入 `manifest.json`，未执行项目始终显示为 PENDING。

阶段二 crossing 采用起飞后 FOLLOW 43 秒，不额外加入人工遮挡，但交叉自然引起的视觉遮挡、几何歧义和失败完整保留。parallel 工程试验同为 43 秒，显式开启短/长人工遮挡及长失后的重新框选。ambiguity 使用 50 秒，预先声明终态应为悬停；这不能用于把普通跟踪失败改判成功。auto_unique 多实例不进行初始框选，目标为歧义安全悬停；显式向 monitor 传入 `--no-follow-duration-s 35`，按无 FOLLOW 场景的仿真时钟停止，不能把墙钟超时当作固定仿真时长。

阶段三在 FOLLOW 后持续 43 秒，长遮挡后显式重新选框，保留重选后至少 5 秒持续跟随的验收窗口。墙钟超时默认 300 秒，属于运行限制，与仿真时长分开记录。

一次只运行一个仿真编排进程。每次飞行进程完成并清理子进程后，串行完成该次所有离线评价，然后才启动下一次飞行。不要同时手工启动另一个共享 PX4 实例、Gazebo partition 或同 ROS domain 的试验。

## 验收与记录

阶段二指定个体试验由 `evaluate_stage2_flight.py` 评价：要求实际多同类新鲜轨迹、框选确认、新鲜度、身份切换授权和最后至少 5 秒持续跟踪。ambiguity 显式使用 `--require-ambiguity --terminal-expectation hover`，要求选定目标发生几何歧义并在记录末尾保持悬停，不能仅凭任务 UUID 不变推断物理身份正确。

auto_unique 多实例使用本脚本的专用评价函数。它要求多帧真实新鲜的同类多框、从未自动进入跟踪、从未发出有效目标运动命令、最后至少 5 秒持续 AMBIGUOUS/HOVER，以及完整的物理速度记录低于 0.30 m/s。缺少速度、状态或命令数据均失败；UUID 为空不构成通过证据。

auto_unique 评价 schema 2 区分检测采集与定时预测：非 projected 的检测快照要求采集年龄不超过 0.75 秒；projected 快照保留上次真实采集时间，长期歧义期间允许这个源时间变旧，但仍须满足有限且有序的采集、输出、接收时间，且不能计入新鲜多框证据。schema 1 曾把所有旧源时间都当成无效，可能误判安全悬停中的合法预测。对已有录制数据重新评价时，保留原报告并另存 `auto_unique_evaluation_v2.json`，明确记录评价器变更，不能覆盖旧失败历史。

阶段三必须同时通过 schema 3 的飞行/遮挡/重选验收和独立云台几何验收。不能仅凭云台命令存在通过。图像中心、真实地平线和机体姿态指标保留在 `gimbal_evaluation.json`，以 `pair_id` 按同 seed 配对，供独立统计分析使用。

每个命令的参数、开始/结束时间、退出码和日志路径即时写入清单。进程退出码为 0 但评价报告失败仍计为失败；缺少报告、缺少 bag 或旧版本飞行报告同样记录失败。失败飞行存在部分 bag 时仍执行评价并保留各项结果。

续跑只执行 PENDING。已失败、已中断的项目不自动重试，不覆盖原试验目录，也不自动把清单外已有目录视作本次成果。硬中断后遗留的运行中状态会标为 INTERRUPTED；需要重新试验时创建新版本 prefix/目录，旧失败仍保留。

`summary.json` 保留计划总数、状态计数、全部未执行 ID 和失败/中断 ID。只有所有计划项均通过时，`all_planned_trials_pass` 才为 true。单次工程验收不替代物理身份标签核验、IDF1/HOTA 或重复试验的配对统计；这些由独立的录制数据研究管线完成。
