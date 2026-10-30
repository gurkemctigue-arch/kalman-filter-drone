# Humble28 汽车检测三配置离线诊断（2026-10-30）

在相同的 170 个原始图像机会、488 个可见车辆标签上，m960 得到 **488 TP / 10 FP / 0 FN**，m1280 得到 **481 TP / 6 FP / 7 FN**，l960 得到 **432 TP / 0 FP / 56 FN**。增大输入分辨率或直接换用 l 权重，均未同时解决局部重复框与漏检；后续应开展针对仿真车辆外观的定向微调，并独立处理可见性几何界的问题。原飞行及阶段验收 FAIL 保持原判。

## 数据与固定协议

四组图像分别为 position11（11 帧、11 车框）、crossing22（22 帧、66 车框）、已有 crossing（93 帧、279 车框）及 multi（44 帧、132 车框）。每配置完整处理 170 个机会，三配置合计 510 次预测；12 组均无未评分机会。可见标签在本次推理前冻结，未知物理身份保持未知并进入检测分母。

这些数据均为开发诊断：已有 137 帧已经参与选型，新增 33 帧针对已知失败窗口抽取。因此，本结果不能作为独立泛化测试、正式多次重复实验或闭环修复的证据。固定 `car` 类置信度 ≥ 0.45、匹配 IoU ≥ 0.5；这里报告该工作点的 TP/FP/FN，不宣称完整 mAP。较大的局部框也可能达到 IoU 0.5，检测 TP 不等于完整车体几何可用。

推理使用 Ultralytics 8.4.188、CPU 4 线程、FP32，全类别返回；模型入口 conf=0.25、NMS IoU=0.7、非 class-agnostic NMS、max_det=300、rect=True、无 augment。m960/l960 实际输入为 `1×3×736×960`，m1280 为 `1×3×960×1280`。保留全部返回类别和框，不因单车场景删除额外框。

## 逐组结果

| 配置 | 图像组 | 帧数 | TP | FP | FN |
| --- | --- | ---: | ---: | ---: | ---: |
| m960 | position11 | 11 | 11 | 4 | 0 |
| m960 | crossing22 | 22 | 66 | 2 | 0 |
| m960 | crossing | 93 | 279 | 2 | 0 |
| m960 | multi | 44 | 132 | 2 | 0 |
| m1280 | position11 | 11 | 6 | 0 | 5 |
| m1280 | crossing22 | 22 | 66 | 2 | 0 |
| m1280 | crossing | 93 | 279 | 4 | 0 |
| m1280 | multi | 44 | 130 | 0 | 2 |
| l960 | position11 | 11 | 11 | 0 | 0 |
| l960 | crossing22 | 22 | 66 | 0 | 0 |
| l960 | crossing | 93 | 262 | 0 | 17 |
| l960 | multi | 44 | 93 | 0 | 39 |

独立复核逐帧重加了全部 510 条结果的 TP/FP/FN，核对匹配、额外框、漏检索引的数量及每帧 `TP+FN=可见标签数`，并验证 62 个输入文件的 SHA256 与正式评分记录一致；没有重新推理或另写匹配算法。三配置各 170 帧、488 个车框的分母及上述合计均一致。

## 缺陷与导航含义

m960 的 10 个 FP 均有至少 80% 的预测框面积落在某个可见车标签框内，是额外局部框的几何迹象。新增原图对照中，position 的 11 个及 crossing22 的 11 个原检测机会，其接受框的类别、置信度、坐标和顺序均逐值复现原记录。position 71.7/71.9/72.1 s 的接受车框数为 2/3/2，而每帧只见一辆完整车；原交集像素预算溢出原因仍在。crossing 64.2 s 的完整中央车被返回为上下两块，随后完整框恢复时已有轨迹竞争。crossing 24.7/24.9/25.1 s 则有三个完整车框，原导航拒绝来自保守深度顺序界，不能归为相同的碎片问题。

l960 在新增 33 帧上消除了该工作点的 FP，但已有两组中新增 56 个 FN。全部返回类别中另有 44 个非 car 框与可见车框达到 IoU≥0.5：36 个 boat、8 个 truck；其中 32 个重叠记录对应 car 未检出，提供误分类迹象。这 44 条包括低于最终 car 阈值的返回框，不能全部当作高置信误分类，也不能解释全部 56 个 FN。例如 multi 50.0 s 对可见车返回 boat，置信度 0.618、IoU 0.991，同时 car 漏检。不能直接把这些非 car 框改为 car，或据此断言 l 已能提供持续导航测量。

m1280 仍有 6 个局部额外框及 7 个漏检；10 条非 car 重叠中，5 条伴随 car 漏检。三配置的离线单帧平均墙钟耗时分别为 0.485、0.944、0.738 s，P95 分别为 0.580、1.089、0.872 s。它们不是在线 ROS 端到端延迟或测量新鲜度，不能据此认定 Offboard 链路通过，也不能放宽原 0.60/0.75 s 保护。

下一步针对重复局部框及 boat/truck 混淆开展微调。首先使用现有图像进行一次 CPU 单轮执行与资源探针：旧 crossing93 与新 position11 为开发训练集（104 帧、290 框），旧 multi44 与新 crossing22 为开发监测集（66 帧、198 框）。两集按完整录制分开，但 crossing 仍共享轨迹族、模型和 seed004，且全部图像已参与选型，不能称轨迹隔离或独立验证；训练所用图像不再作为未见样本。探针不能作为最终模型，原权重及标签保持不变。

后续候选与阈值冻结后，须使用预留的新开发种子及新视点/场景验证，并按完整轨迹族隔离独立测试。正式种子 1000–1009 仍不使用。可见性保守界、身份关联、在线时序及全阶段实验仍需各自验收。

## 本地证据与 SHA256

外部目录为 `D:/WSL/UAVHumble22-validation/`。路径中的大型原图、预测和模型不随本文自动提交；正式评分文件绑定全部 12 组的 manifest、标签、预测、warmup 和源文件摘要。

| 本地路径（相对外部目录） | SHA256 |
| --- | --- |
| `humble28_car_detector_diagnostic02/operating_point_metrics01.json` | `69a5f60069b45329478f32d2095bb3a1c1925e7a857b6f825b202d2db9d55f47` |
| `humble28_detector_diagnostic02_independent_audit01.json` | `cf177cfff4f29b9f984d161dea878cf35cde78476a1dda1574e91b8df579f50d` |
| `humble28_postfreeze_m960_reproduction01.json` | `39684c8b4ac01ad0a13307d8b7e47825f8ade9c207523eed4e79d87295c44284` |
| `humble28_car_detector_diagnostic02/position11/visible_labels.json` | `62b1cb3886b551ce3ae248276eab4406ae6bfa7ff73f9c1da97fd2e6a1086b5a` |
| `humble28_car_detector_diagnostic02/crossing22/visible_labels.json` | `18d9e3955526030b6f969e95b8c7d393814298e2aea60b136ea60b6da43d95b2` |

已有两组原图和标签目录为 `humble25_car_detector_study01/`、`humble25_car_multi_detector_study01/`；新原图目录为 `humble28_car_detector_diagnostic02/{position11,crossing22}/raw_rgb/`；12 组全部预测位于 `humble28_car_detector_diagnostic02/paired_predictions01/<corpus>/<candidate>/`。

m 权重 SHA256 为 `d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95`；l 候选下载文件 SHA256 为 `9ebd0e09d59811db4b1d61e2bc6730649608b1ac47f8dd01e2da6bca7c20023f`。l 来源固定官方 v8.3.0 下载 URL，实际下载摘要已记录，官方独立发布 digest 尚未核验。
