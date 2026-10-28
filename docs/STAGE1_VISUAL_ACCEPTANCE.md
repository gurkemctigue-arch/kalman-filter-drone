# 阶段一成果可视化验收指南

阶段一已经保留了两类验收证据：机载相机视频和逐时刻截图用于人工观察，rosbag 与离线 JSON 报告用于复核状态机、遮挡事件和 PX4 设定值。它们位于本地 `results/` 归档，不随公开源码提交；归档边界见 [结果工件说明](RESULTS_ARTIFACTS.md)。建议先看视频，再用报告核对结论。

## 建议观看顺序

1. `results/stage1_final_v2_person_velocity/onboard.mp4`（行人/速度模式）
2. `results/stage1_final_v2_car_position/onboard.mp4`（汽车/位置模式）
3. `results/stage1_final_v2_person_position/onboard.mp4`（行人/位置模式）
4. `results/stage1_final_v2_car_velocity/onboard.mp4`（汽车/速度模式）

Windows 中直接双击 MP4 即可播放。视频来自机载 RGB-D 相机画面，画面上的绿色框、`YOLO` 置信度、`D` 距离以及 `FOLLOW/HOLD` 状态是监控器叠加信息。

## 观看时检查什么

- 正常跟随：目标在绿色检测框内，画面中有 `FOLLOW`，无人机和目标都在运动。
- 短时遮挡：目标暂时消失后，系统进入预测但不应立即进入 `LOST`，目标重新出现后身份和跟随应恢复。
- 长时遮挡：目标消失时间足够长后应进入 `HOLD/LOST`，无人机减速并悬停；目标重新出现在画面中也不能自动恢复。
- 重新选框：只有测试脚本发出新的选择后，才会恢复跟随。汽车位置模式的末帧截图位于 `results/stage1_final_v2_car_position/frame_00301.jpg`；它显示 `FOLLOW`、`YOLO 0.88` 和 `D=9.78m`。

行人速度模式的一张末帧截图位于 `results/stage1_final_v2_person_velocity/frame_00301.jpg`，可以看到行人、绿色检测框、置信度和距离叠加。

此外，已从每次试验的 `telemetry.jsonl` 生成四张辅助汇总图：

- `results/stage1_visual_report/stage1_final_v2_person_velocity.png`（行人/速度模式）
- `results/stage1_visual_report/stage1_final_v2_car_velocity.png`（汽车/速度模式）
- `results/stage1_visual_report/stage1_final_v2_person_position.png`（行人/位置模式）
- `results/stage1_visual_report/stage1_final_v2_car_position.png`（汽车/位置模式）

每张图包含飞行器水平轨迹、速度、RGB-D 深度观测和阶段/遮挡/重新选框时间线。它们是从原始记录绘制的辅助视图，视频、rosbag 和 JSON 才是可追溯原始证据；重新生成图表可运行 `python scripts/plot_stage1_acceptance.py`。

## 用报告做正式核对

打开本地归档中的 `results/stage1_final_v2_report.json` 可以看到四组结果均为 `PASS`。每一组的 `results/stage1_final_v2_car_position/offline_evaluation.json` 等离线评价 JSON 还记录了短遮挡、长遮挡、悬停、显式重新选框、重选后持续跟随和 PX4 设定值互斥检查。

汽车位置模式是最适合重点验收的一组：长遮挡后在 `54.68s` 确认新目标 UUID，随后持续记录 `11.24s` 状态和 `11.20s` 跟随控制，直到试验记录结束；期间没有再次 `LOST`、UUID 变化或非跟随控制。四组原始视频、rosbag、配置和源码哈希都位于各自的 `results/stage1_final_v2_*` 目录。

## 可视化证据的边界

视频可以直接证明“相机确实看到目标、检测框跟着目标、无人机在运动、遮挡和恢复发生了什么”。它不能单独证明 mAP、IDF1 或精确三维误差；这些指标需要标注数据或独立真值对齐。当前阶段一的正式工程结论由视频、rosbag、离线评价和[验收记录](STAGE1_ACCEPTANCE.md)共同给出。

已有的 `results/synthetic_estimator_baselines.json` 包含 10 个随机种子、行人与汽车两类目标以及 raw/EMA/fixed-KF/adaptive-KF 四种方法，共 80 条配对记录。它属于算法基线重复实验，不等同于 PX4 闭环重复；闭环重复仍需单独运行仿真矩阵。
