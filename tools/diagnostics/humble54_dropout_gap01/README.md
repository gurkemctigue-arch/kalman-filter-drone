# 短挡板原图与输入时间戳提取

当前入口支持原计划 `dropout` 与 `combined` 两种包含 10% 整帧丢失的工况。首份实际导出使用的 v01 仅支持 `dropout`，其[原脚本字节](evidence01/extract_short_window_v01.py)和原 manifest 的工具 SHA 一致；新增工况支持不冒充已经执行过该工况提取，后续仍须统一绑定实际使用版本。

`extract_short_window.py` 是一次性只读诊断工具。它核对原计划/终态内容摘要、任务名称、原非基础设施退出与清理证据、闭包/完整性小报告、surface 报告和原 `open_bag_reader` 源 SHA；另将原 `rosbag/metadata.yaml` 和 `configuration/sensor_faults.json` 的小文件字节与 terminal artifact SHA 绑定，检查 seed 与计划一致、`drop_fraction=0.10`。随后提取唯一短挡板窗口前后各 0.3 秒的全部 raw RGB。超过 32 帧直接失败，不抽取较好的帧；部分失败目录保留，禁止覆盖。

仅在原生任务全部闭合且空闲、加载原 Humble54 ROS/Python 环境后执行。输出必须是冻结源码及原 matrix/trial 之外的全新目录，例如：

```bash
bash /root/uav_tracking_fullplan_v4_humble54/scripts/run_research_session.sh \
  /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/humble54_dropout_gap01/extract_short_window.py \
  --source-root /root/uav_tracking_fullplan_v4_humble54 \
  --plan /root/uav_tracking_fullplan_v4_humble54/results/reliability_v4_humble54_extension16_probe01_matrix/plan.json \
  --slot-id person_extension_dropout_seed004 \
  --output /mnt/d/基于yolo和卡尔曼滤波/results/diagnostics/humble54_dropout_gap01_extract01
```

复用原 reader 的临时解压策略，不写原 bag。只读取 Clock、raw/research RGB、raw/research Depth 和 detection diagnostics 六类话题，不读取真值或模型，不推理。扫描完整的固定话题集合，以保留乱序或较晚到达、采集戳仍在窗口内的所有机会。`record_sequence` 是这六类过滤后读取顺序，**不能与旧 evaluator 的不同过滤集合序号直接比较**；每条还保留 recorder 时间戳和最近已读 Clock。图像 header 的整数纳秒精度保留；diagnostic 优先使用原 JSON 的整数 `acquisition_ns` 精确选窗，同时保留原 `stamp_s` 十进制和完整原始文本。只有缺少 `acquisition_ns` 字段时才使用来源秒戳精度，字段存在却不是整数则拒绝；不会伪造 diagnostic header。

输出有原尺寸无框 PNG、含全部原图缩略图的 `contact_sheet.png` 和 `manifest.json`。原图只作无损通道排列；缩略图单独缩放并附序号/时间标签。manifest 原样保留旧短窗 checks/null、旧 acceptance 和全部实际窗口机会；成功提取仍为 **`PENDING_VISUAL_REVIEW`**。缺帧不等于空检测，不自动判定渲染遮挡，不生成新 PASS、准入或更改原 `INCOMPLETE_EVIDENCE`。

准备阶段已检查 Python AST/语法与 `--help`。2026-11-03 实际调用在原生空闲窗口完成，独立 owned monitor 记录退出 0；原始提取输出位于 `results/diagnostics/humble54_dropout_gap01_extract01`。其 [9 张原图与清单](evidence01/manifest.json)、[联系图](evidence01/contact_sheet.png)及[独立阅图记录](evidence01/visual_review01.json)另作逐字节归档，原提取 manifest 仍保持 `PENDING_VISUAL_REVIEW`，新增阅图记录与它分开保存。

两名代理分别查看联系图及 31.4、31.5 秒两张原尺寸图：这两帧整体近黑、看不到目标；前后帧能看到行人。短请求窗内有 3 帧 raw RGB/Depth，research RGB/Depth 与检测诊断均为 0；31.3 秒原图仍可见目标，早于 31.32 秒 close ACK。全选窗口保留 9/9 帧 raw RGB/Depth、5/5 帧 research RGB/Depth 和 5 条诊断，Clock 回归为 0。它补充上游画面与输入机会的观察，不能区分遮挡和注入掉帧对预测的单独贡献，也不改变原 `null`、`INCOMPLETE_EVIDENCE` 或正式准入。
