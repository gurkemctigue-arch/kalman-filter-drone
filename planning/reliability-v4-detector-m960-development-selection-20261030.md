# YOLO11m/960 作为新闭环开发候选的选择决定

本次选择 `models/yolo11m.pt`、推理尺寸 960、CPU 4 线程、跟随距离 9.0 m，供下一轮汽车闭环开发验证。它尚未成为正式采用的模型，也没有证明原汽车失败已修复。预注册文件仍为 `DRAFT_NOT_FROZEN_NOT_EXECUTED`；正式试验仍为 0/280，留出的 1000 至 1009 种子尚不授权使用。

## 离线依据

五种配置使用同一 crossing 93 帧 / 279 可见框和 multi 44 帧 / 132 可见框，固定 predict confidence 0.25、最终 car confidence 0.45、匹配 IoU 0.5、全类别输出、CPU 4 线程及 FP32。下表依次为 TP / FP / FN：

| 配置 | crossing | multi |
| --- | --- | --- |
| YOLO11s/640 | 275 / 12 / 4 | 112 / 7 / 20 |
| YOLO11m/640 | 267 / 0 / 12 | 96 / 0 / 36 |
| YOLO11s/960 | 274 / 20 / 5 | 129 / 7 / 3 |
| YOLO11s-seg/640，仅评价框 | 226 / 0 / 53 | 100 / 0 / 32 |
| **YOLO11m/960，本轮候选** | **279 / 2 / 0** | **132 / 2 / 0** |

YOLO11m/960 在 multi 的中央 `stage2_car_0` 重选后窗口得到 23/23 正确车框匹配，没有该窗口中的已标注漏检；这支持将其用于新闭环验证。局部额外框仍存在：crossing 的 25.6、25.8 s 各一个，multi 的 26.8、27.3 s 各一个，均为可见车上部的局部框。crossing 这两帧的物理身份标签未知，只能称为与 frame-local GT 框重叠，不能补成已知物理车。多个候选引起的歧义仍须按原安全策略处理。

crossing 中 47 帧的 141 个框没有显式物理身份。这些框完整参与检测 TP/FN，使用 frame-local GT index；只有显式非空 `physical_id` 才进入跨帧逐车统计，`proposal_id` 仅为原标注元数据。未知身份不会补成已知身份或连接缺失段。多种候选来自同一批相关开发帧，不能据此宣称正式泛化、完整 mAP、身份保持或卡尔曼滤波优势。

## 时效限制

本轮离线 `predict + 框转换 + 线程/精度检查` 的实际墙钟时间如下，单位为秒，排除原图解码和 warmup：

| 语料 | 帧数 | 中位数 | P95 | 最大值 |
| --- | --- | --- | --- | --- |
| crossing | 93 | 0.479620 | 0.581024 | 0.697101 |
| multi | 44 | 0.529150 | 0.718313 | 0.854600 |

这些是离线顺序推理耗时，不是在线 FPS、端到端延迟或测量新鲜度。墙钟耗时不能直接代替仿真 ROS 时钟下的图像采集至发布年龄。新的同源闭环须实际检查 CPU 负载、实际实时率、检测间隔、采集与发布时间、控制有效覆盖率及原时效门，才可判断 m960 能否用于系统。

0.60 s 观测新鲜度、0.75 s 预测、马氏距离门 9.21、歧义暂停、长丢失后显式重选均保持不变。不能为慢推理延长这些边界，不能丢弃失败样本，也不能以离线零漏检代替完整跟随、身份和稳定性验收。

## 来源绑定与下一步

- 官方 `yolo11m.pt`：40,684,120 字节，SHA-256 `d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95`。
- 本轮前瞻计划：`planning/reliability-v4-detector-m960-candidate-20261030.md`，SHA-256 `af1e83e7107e0a7573fc7452dd1f10d1c59f8ff653fe554167c666d99f69f9db`。
- m960 实际评分：`humble25_car_detector_candidate_m96001/operating_point_metrics_root01.json`，SHA-256 `519653d9a4663efc30fd2f1ecbe80e153c02b314f0e12f26e8eec5959891ea0b`。
- s960 / seg640 实际评分：`humble25_car_detector_candidates02/operating_point_metrics_root01.json`，SHA-256 `2afa7246ef7c43225150b7de6f25606db78d598c8884096211a061c1451efc42`。
- s640 / m640 crossing 实际评分：`humble25_car_detector_study01/paired_predictions02/operating_point_metrics.json`，SHA-256 `eb3b303b3201e7f7d8471d4bb3ed96c4870d2433b2413eb7835255e6ebc4ca87`。
- s640 / m640 multi 实际评分：`humble25_car_multi_detector_study01/paired_predictions/operating_point_metrics.json`，SHA-256 `82b9c15205994fceaea2315cb260ae6c664b3e7e97b5c1acc08cb6a071297b55`。

以上评分位于外部 `D:\WSL\UAVHumble22-validation` 目录，原图、标签、旧源、首次评分失败与全部结果保持不变。此次只更新汽车资源草案和尚未执行的 Humble26 准备 helper；不发布 final review、enable 或 freeze。下一步仍须独立审核最终来源、冻结并构建，通过新的 20 s clean 执行检查，再进行同源 12 核心 / 4 安全 / 16 扩展和完整 75 s 验证；原 Humble25 的 9 PASS / 3 FAIL 保留，不以新候选结果覆盖。
