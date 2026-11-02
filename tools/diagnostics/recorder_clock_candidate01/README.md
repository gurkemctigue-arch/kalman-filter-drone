# 真实录包 /clock depth 组件对照

一次命令只执行一个条件，不自动重试、不自动续跑另一条件。原始仪器已原字节归档为 `archive_v1/probe_recorder_clock.py`，SHA-256 为 `868689fd2ebee216f0030f6c96eacd5e2b97bf51b454f5d79881cd492648492e`；下表四个原条件和已有报告保持原样。

| 原条件（诊断发布 depth10，recorder 自动发现） | 非clock证据 | Clock 录入/观察 | producer差值范围 | 原参考门越界 |
| --- | --- | --- | --- | --- |
| current2048，暂停0.6墙秒 | 完整 | 5055/5055 | −44～+4 ms | 0 |
| candidate1，暂停0.6墙秒 | 完整 | 5088/5105 | −4～+60 ms | 0 |
| current2048，暂停1墙秒 | 完整 | 5107/5107 | −68～+4 ms | 5 |
| candidate1，暂停1墙秒 | 不完整 | 5029/5055 | 0～+72 ms | 0 |

第四条件三类图像均有200帧且内容完整，末clock闭合，但 producer 发送2225条、录入2224条；缺失 `event_id=1104`，源 receipt 为10.04秒，处于人工暂停期间。因此其原状态 `INCOMPLETE_NONCLOCK_OR_CLOCK_TAIL_EVIDENCE` 保持，零参考门越界不能将它升级为通过。诊断队列自身容量是混杂因素，新配对须使用相同的1024诊断历史重新采集。

它复用原 `clock_isolation_candidate01/probe_split_rgbd01.py` 的原字节（SHA-256 `1ec86d74d846f31a151db28b0db1c1246c298c9d2975f8f08fbe1c9f1924a892`），只在新 loader 中重绑定 ROOT/BASE/OUT 到 Humble53 及新输出。原生产阶段三 640×480、10Hz RGB-D、4ms物理步长、RTF 0.125、独立时钟/数据桥和原 runtime/DDS 验证、进程所有权及退出逻辑保留。新 envelope 添加真实 sqlite3 recorder、独立 ROS receipt producer、完整非时钟证据核对；不运行 PX4/YOLO，不证明飞行修复。

两个条件为 `current2048` 和 `candidate1`。完整复制原 `config/recording_qos.yaml`（SHA-256 `d56c368ecba5e77a7343a7832be4ec234a4cd4576e367aaa9a808c356cf76824`），语义差异仅为 `/clock.depth`：2048 或 1；`keep_last`、`reliable`、`volatile` 及其他 profile 保留。原方案、旧报告与时效门不改。

新增可选 `--producer-evidence-depth`，只接受10或1024，默认10保持原发布历史和自动发现的录包行为。1024模式为诊断 `producer_receipt` 和 `capture_control` 的发布者及recorder显式选择 `keep_last/reliable/volatile/depth1024`。三类图像观察订阅仍为depth10，原五项生产profile全部保留；同一诊断深度的配对中仍只有 `/clock.depth` 不同。result记录本次执行probe和原输入source pins、请求的发布及recorder诊断QoS；未独立认证实际endpoint QoS。

## 原生前置与命令

仅在 root 决定开始后，使用独占空闲的 `UAVHumble22`，不要与仿真、推理或其他重任务并行。需要原 Humble venv/overlay、ROS-GZ shutdown A01、Fast DDS listener A01 注册，以及原模型资源。输入脚本从 Windows 挂载目录读取，录包建议写新 ext4 目录；至少4GiB空闲，每条件保留原始bag，上限2GiB。

```bash
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble53
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
source "$HUMBLE22_PROJECT_ROOT/scripts/humble22_env.sh"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p /root/uav_tracking_bag_spool/recorder_clock_candidate01
```

先运行当前条件；以下两条不能并行，第二条应在第一条完整退出后单独调用。这里使用相同的 **0.6墙秒人工 recorder 暂停**，每条件一次，不代表生产行为。

```bash
/root/uav_humble22/venv/bin/python -B /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/recorder_clock_candidate01/probe_recorder_clock.py run --source-root /root/uav_tracking_fullplan_v4_humble53 --base-probe /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/clock_isolation_candidate01/probe_split_rgbd01.py --condition current2048 --output /root/uav_tracking_bag_spool/recorder_clock_candidate01/current2048_pause06_01 --stress-recorder-pause-wall-s 0.6
```

```bash
/root/uav_humble22/venv/bin/python -B /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/recorder_clock_candidate01/probe_recorder_clock.py run --source-root /root/uav_tracking_fullplan_v4_humble53 --base-probe /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/clock_isolation_candidate01/probe_split_rgbd01.py --condition candidate1 --output /root/uav_tracking_bag_spool/recorder_clock_candidate01/candidate1_pause06_01 --stress-recorder-pause-wall-s 0.6
```

省略 `--stress-recorder-pause-wall-s` 时为0，不暂停。可显式选0.6或1.0，其他值拒绝。暂停在首个观察clock后+10源秒触发，只向身份已核对的自有recorder进程组发一次SIGSTOP，单调墙时到期后SIGCONT；任何异常退出都先尝试SIGCONT，再清理。完整记录实际暂停时间、源时刻和PID身份。两条件必须使用相同stress设置，人工压力结果单独解释。

薄入口 `run_native_condition.sh CONDITION [PAUSE_WALL_S] [PRODUCER_EVIDENCE_DEPTH]` 的第三参默认10。新1024配对由主执行者串行运行：

```bash
bash /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/recorder_clock_candidate01/run_native_condition.sh current2048 1.0 1024
bash /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/recorder_clock_candidate01/run_native_condition.sh candidate1 1.0 1024
```

输出分别为 `current2048_pause10_proxy1024_01`、`candidate1_pause10_proxy1024_01`，已有目录会拒绝，不覆盖原四条件。新配对已真实串行完成，见 [独立小原件与比较](evidence_proxy102401/comparison.json)：两组固定窗口三类各200帧、全部producer/control、末Clock闭合及进程清理均完整，执行probe及全部原输入pin相同，QoS唯一条件差异为Clock depth。旧组仍5次原参考界越界（−68至+4ms），候选组0次（0至+92ms）；候选少录28个Clock，最大源步长96ms。原V1不完整条件继续保留。生产depth1据此成为新完整飞行的待验证候选，不能保证全部消息满足原50ms相关门限，不补clock、不放宽阈值，也不推断PX4、YOLO或完整飞行已修复。

原Humble53的672字节profile已原字节保存于 `archive_v1/recording_qos.yaml`，SHA仍为上述 `d56c…6824`。便携检查核对此独立归档；当前生产profile的有意depth1改动不冒充原对照输入。原Humble53配置和六份原条件报告均未重写。

## 结果含义

- `started.json`、`result.json` 保留运行配置、源文件pin、请求及实际 `/proc` 命令、自有PID、子组件与recorder退出码、强制终止/残留情况。原组件的真实桥 runtime/DDS 证据、原生产模型和三个自有进程清理记录位于 `base_capture/`。
- 看到首个RGB/Depth/Info且recorder读者已匹配后，预先登记“未来100ms保护＋固定20源秒”窗口，不能录完后按可用bag交集裁剪。原组件已有20源秒观察；若匹配太晚，登记窗口未完整覆盖，结果保持不完整，不缩短窗口补通过。
- 全部选定bag原序读取并与metadata计数核对，SQLite只读完整性检查。固定窗口每类图像必须200–201个独立源时间戳、符合10Hz/4ms节拍；RGB/Depth逐帧像素摘要、完整CameraInfo标定摘要与独立观察ledger的多重集必须一致。所有producer/control发送记录也必须完整相等。窗口外数据保留，不用于填补窗口内缺失。
- 独立producer同时保存100源Hz ROS timer和RGB回调的真实ROS receipt，以及独立单调/系统墙时样本；这只是时间参考proxy，不是PX4 adapter、源数据新鲜度或因果端到端测量。其与bag中最后已出现的 `/clock` 的差逐条保留，不能把跨writer排队直接判为运行时钟坏。
- `clock_record_sequence.json` 保留每条clock原序、源时间及原record ns间隔，显示缺步、重复、回退及大gap。未独立认证record timestamp的墙时域，因此使用原始记录时间间隔标签，不跨域相减。末clock必须追上最后图像、END producer clock和独立观察clock，否则不完整。
- `COMPONENT_EVIDENCE_COMPLETE_NO_REPAIR_CLAIM` 只表示这一条件的证据链收齐。clock少录不授予成功；保留全部数量/gap/producer-reference异常与非clock缺失。单条件不声明对照改善、生产修复或飞行验收，原FAIL保持。退出码0只对应组件证据完整，其他情况为2。

## 便携纯检查

```text
python -m unittest discover -s tools/diagnostics/recorder_clock_candidate01 -p test_probe_recorder_clock.py
```

本次在Windows实际运行6项检查，全部通过；覆盖参数/惰性describe、诊断深度的配对隔离与输入不变、原始仪器及生产输入字节、自有身份保护下的SIGCONT清理、非clock完整分母。无ROS、bag或进程启动；不替代原生两条件运行。薄入口另通过原生Git Bash的 `bash -n` 语法检查，未调用WSL。
