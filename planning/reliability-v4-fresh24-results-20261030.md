# 固定新24视角：第二轮汽车模型配对检查结果

2026-10-30，固定`train20_04`框架best（epoch17）完成新24视角检查。48/48次预测成功、0未知，完整24逐图配对保留；按事前“原m正确而候选新增漏检/误检，或明显局部框退化则不直接替换”规则，**本组未触发拒绝条件**。根代理和独立审查代理均实际查看全部三页三列对照图，未见明显局部框退化。这只支持进入新Humble29开发闭环，不是工程验收或正式研究通过。

| 指标 | 原YOLO11m/960 | 固定train20_04 best/960 |
|---|---:|---:|
| 图像机会 / 已评分 / 未知 | 24 / 24 / 0 | 24 / 24 / 0 |
| TP / FP / FN | 24 / 1 / 0 | 24 / 0 / 0 |
| 空背景机会 / 空背景FP | 6 / 0 | 6 / 0 |
| 匹配IoU通过但GT覆盖低于0.8 | 0 | 0 |
| 最小匹配GT覆盖 | 0.9554341 | 0.9691568 |
| 最小匹配IoU | 0.9554341 | 0.9507869 |

候选没有逐图新增FP或FN，也没有新增低覆盖诊断。原view017有一个额外后车身局部重复框（置信度约0.615），候选保留两辆车的完整可见框并移除该额外框。少量边缘及IoU差异仍存在，不声称所有几何指标都改善。236图开发监测中的已知view038跨两车合并框误检仍保留，必须在闭环中验证其轨迹竞争/歧义风险，不能用本组零FP消去它。

24机会事前固定为12单车、6双车、6空背景，使用开发seed007/Gazebo8、3批各8视角。保留原240条RGB/CameraInfo消息、480个原始文件；每个机会只使用原先约定的第五个唯一RGB。24张原PNG全部逐张查看，结合实际CameraInfo K的离线mesh投影辅助标注，复核可见像素和叠图后冻结：24个可见汽车框、4个部分遮挡、0未解决/截断，所有`physical_id=null`。盲标冻结时间为10:07:08 UTC，比较输入冻结时间为10:11:29 UTC，均早于本组模型推理；预测没有参与选帧或标签修改。

预测/评分保持原car=2、置信度0.45、一对一IoU0.5（原1e-12容差）、覆盖0.8诊断，全类别预测conf0.25/NMS0.7不变。独立复核未导入原评分实现，重算全部48预测的匹配、FP/FN及几何指标，并核对原图/标签SHA、全部48预测与2次warmup的CPU FP32实际`[1,3,736,960]`输入和4线程记录。未知、空背景和所有额外框均完整保留。

## 本机证据及SHA-256

以下目录均在本机`D:/WSL/UAVHumble22-validation/`，原文件和失败不覆盖；表中路径相对此目录。

| 证据 | SHA-256 |
|---|---|
| `humble28_car_holdout_views02/source_receipt.json` | `53b61cace04b476ced470bae9d82679c41f5972e6b5a9f3b23a250eb523a5dfa` |
| `humble28_car_holdout_views02/raw_capture_seed007_gzseed8/experiment_terminal.json` | `ad64589ac1b5732be23f6eb86b34ef1871ed0645d622c56ee1525a6c77e91173` |
| `humble28_car_holdout_views02/raw_manifest.json` | `4b4ee889200e84d1021751a5d23065499d50382603d0e3ff49bd897ee4ab25df` |
| `humble28_car_holdout_views02/visible_labels.json` | `bc4900e5e20beff2836144f1335b96d3b39c8e0c18abdaa5e2029343e961f679` |
| `humble28_car_holdout_views02/postprocess01/visible_label_review_receipt01.json` | `b630b714491e9d939c4f283295cf312f5d1b8d70cd25f2b0149f8e5c766e9a0d` |
| `humble28_car_holdout_compare02/frozen_inputs01.json` | `25693010bb228dec6d2df6ac32844fc7ff5f4e4ecd3dae20258e3cdc6312f03c` |
| `humble28_car_holdout_compare02/predictions01/all48_outcomes.jsonl` | `14695ea0697507a40a7bf535f50c2a1d3dc1d4bfb673de36bbc5cdebb6f4cd2b` |
| `humble28_car_holdout_compare02/operating_point_metrics01.json` | `5b6577b09e2ba73ec06d96b0bb458baa2c1f958094e6a33e5847452e9e8a5bbb` |
| `humble28_car_holdout_compare02/paired_regression_audit01/summary.json` | `10f8359ec65358ca1bd422b282091b46ebb0eac900f30de8a7630418c1cca747` |
| `humble28_car_holdout_compare02/independent_audit01.json` | `9e435e56bf0ba7d7e1a88bb5b5add46d4931c3631fdab52c39c0c68eb84fc145` |
| `humble28_car_holdout_compare02/independent_visual_attestation01.json` | `b48c8d7c93e6f0d1cdc9a470f510dd3b53c3857ff28904c59fae6963e42539c4` |
| `humble28_car_holdout_compare02/visual_diagnostic01/inventory01.json` | `b580115c367df6f122c34f4ff82f3ec68c05d51799da71a7f04cf35e28b84745` |

数值审计原文件如实保留其当时的“视觉待复核”状态，后续实际视觉完成由独立attestation绑定，不改写原记录。三列图依次为未加框RAW、原模型全部car0.45框、候选全部car0.45框；每页8个机会，另有24份原尺寸单机会条带：

- [三列第1页](D:/WSL/UAVHumble22-validation/humble28_car_holdout_compare02/visual_diagnostic01/comparison_montage_page01.png)
- [三列第2页](D:/WSL/UAVHumble22-validation/humble28_car_holdout_compare02/visual_diagnostic01/comparison_montage_page02.png)
- [三列第3页](D:/WSL/UAVHumble22-validation/humble28_car_holdout_compare02/visual_diagnostic01/comparison_montage_page03.png)

## 下一开发来源

根代理决定仅将固定第二轮best作为新Humble29开发闭环候选，并独立显式启用已完成原帧回放验证的`navigation_correlated_two_face_bound`；检测模型选择不会隐式开启几何开关。下一步按[精确模型登记](reliability-v4-model-adaptation.md)复制best、infer04收据和第二轮数据manifest的原字节，分别核SHA，保留原模型及所有旧失败；不换epoch、不重排receipt或改写历史路径。

随后以新来源冻结、四个ROS包冷构建、真实CDR往返及Linux检查，再从同一来源运行两类clean、12核心、4安全和16扩展开发门。新29的这些工作在本结果记录时尚未执行，不能拼接旧来源的PASS；原0.60秒观测/0.75秒预测与身份/丢失/歧义保护不变。主树协议的候选选择仅服务新开发来源，正式整体仍为`DRAFT_NOT_FROZEN_NOT_EXECUTED`、**0/280**；正式seed1000至1009不用于开发。

新24仍来自同一Prius资产和渲染器，只是新的固定视角/背景开发检查，不能证明跨车型、实机泛化、身份保持、在线实时性或闭环飞行可靠性。原Humble28核心8 PASS/4 FAIL保持，尚无Humble29工程验收通过结论。
