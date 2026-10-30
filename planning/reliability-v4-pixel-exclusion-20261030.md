# 导航排除框统一采用被触及的像素单元

当前 detector 的 `navigation_overlap_evidence` 和 visibility 的 `overlap_pixel_rectangle` 已使用像素单元 `[u,u+1)×[v,v+1)`：先确认连续框交集有正面积，再将交集低界 floor、高界 ceil，保留所有被触及的原始深度单元。`sample_depth_points` 的排除框此前直接用整数采样坐标比较连续边界，与该契约不一致。

已有精确诊断表明：原 25.6 秒 selected exclusive 点投影到 `(361,203)`，其他框的 xmin 为 361.2589。整数 361 小于该连续边界，旧排除规则保留此点；同一个像素单元却被完整 overlap 证据正确计入。这里不重新读取或修改旧 bag、冻结来源或 geometry 工件。

新来源只修改 `sample_depth_points` 的 `exclude_bboxes` 语义：保留 finite/形状检查；连续框的任一维零面积或负面积时为空排除，必须在 rounding 前判断；其余框以低界 floor、高界 ceil 覆盖全部触及单元，裁剪至图像范围，按 half-open 区间排除。禁止通过 rounding 将退化框变成正面积。

主 bbox 的向内采样边界、网格起点、stride、自适应 stride、cap 和深度有效性不变。共享 helper 同时用于目标 exclusive 支持和 ground 排除；同类及跨类的全部已检测框仍参与排除。目标原完整 cloud、完整 overlap 区域/计数/原深度不删减；检测模型、支持数门限、歧义和身份策略不改。

本次仅运行主机 fixtures，检查分数边界、边/角、整数端点、子像素非交叠、退化与图像外框、排除后点集和 ground/cross-class 连接，以及完整 overlap 仍保留原像素。新导航来源须进入 root 的新 freeze/review 和 Linux 闭环验证；不得更新旧 replay helper SHA 期望或重写旧结果。
