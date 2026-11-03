# probe02 combined：已有小 sidecar 的描述性诊断

当前解释采用 `sidecar_evidence03.json` 与 `combined_failure_timeline03.png/.pdf`。
原工程 FAIL、bag、telemetry 及原评价报告均未修改；本分析不读取 bag/telemetry，不运行 ROS/仿真。

FOLLOW 评价窗内导航在 34.84 s 有效、34.86 s LOST；末次接受参考 source34.1，下一参考 source34.8，后者 sidecar 有效仿真时刻34.904，已无被接受的指定目标观测。
记录故障规则预期34.2–34.8连续DROP，但实际RGB/Depth投递尚未在本次分析中独立确认。原生33.8–35.2 s取证仍待空闲窗口。

时间语义已对照冻结评价器 SHA `bbff6c746ed76d0139c194cdfc1409f38dc422d64ddbc73da2995a0838df4422`：

- 126–127行 `_operational(record)` 为source与记录接收时刻的最大值，接收缺失则回退source。
- 312–317行诊断分支还与有限 `output_s` 取最大值，433–449行写入 `raw_frames.received_sim_s`。
- `message_frames.received_sim_s` 写入状态记录的 `_operational(record)`（505行）。

这些字段不是精确回调或物理墙钟时延。v1误称记录接收、v2只说明了基础`_operational`而未区分诊断`output_s`；原版本的证据、图和当时执行源码全部保留，数值不变，v3补齐解释并在读取时核六项原终态SHA。图中阴影仅表示规则预期，不能充作实际投递证据。

`analyze_sidecars.py` 和 `plot_sidecars.py` 记录当前执行源码SHA，输出仅允许新文件；本次实际生成完成。原输入须在同一项目原路径可用，不能以复制后的未知数据替代。

## 待执行的原生输入取证

`extract_raw_window.py --describe` 已执行，仅返回准备状态，未打开实验输入。实际提取复用 SHA 固定的原 short-window exporter，原 bind 完整复核不变；只把选择窗明确改为33.8–35.2 s并标注不能用于sensor4。运行期间持有既有SITL互斥锁并核原生idle，禁止与当前collector或runner08并发。

以下命令仅在06/07/09/08真实退出、所有重型子进程闭合之后，使用原Humble研究环境执行。输出目录须全新，失败产物保留，不重试覆盖。

```bash
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble54
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export TMPDIR=/tmp STAGE1_TRANSIENT_DIR=/tmp PYTHONDONTWRITEBYTECODE=1
source /root/uav_tracking_fullplan_v4_humble54/scripts/humble22_env.sh
bash /root/uav_tracking_fullplan_v4_humble54/scripts/run_research_session.sh \
  /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/humble54_probe02_combined_sidecar_review01/extract_raw_window.py \
  --execute-after-native-idle \
  --source-root /root/uav_tracking_fullplan_v4_humble54 \
  --plan /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix/plan.json \
  --slot-id person_extension_combined_seed004 \
  --output /mnt/d/基于yolo和卡尔曼滤波/results/diagnostics/humble54_probe02_combined_raw_window01
```

该导出只提供原始图像与bridge/diagnostic话题的逐机会存在性，仍不能独自回答关联打分与精确controller转变；相应小型telemetry窗口需在空闲后另行核查。当前上述native命令尚未运行。
