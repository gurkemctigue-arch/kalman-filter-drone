# Humble53 行人交叉开发场：105 格身份未知的实际证据

对象：`reliability_v4_humble53_probe01_person_stage2_crossing_seed004`。
本卡只读分析该场实际 `physical_identity.json`（1,659,511 字节）与
`stage2_evaluation.json`（18,235 字节），不重跑评价、不读 bag、不启动 WSL、
不修改原报告或验收定义。两份文件的 SHA 均与主代理给定值一致；本卡不是新验收门。

## 原分母与两次任务

原保守指标从首次明确 REQUEST **17.6 s** 到最后记录 `/clock` **92.852 s**，
使用固定 0.1 s 单元，保留最后不足 0.1 s 的单元：
**753 格 = 648 正确 + 0 已知错误 + 105 未知，已知覆盖率 86.0558%。**

| 任务 UUID | REQUEST / 确认时间（s） | 正确 / 全部单元 | 未知 | 初始独立映射 |
| --- | --- | ---: | ---: | --- |
| `1347b05e-53cd-4c12-a96b-a34225873eda` | 17.6 / 17.684 | 218 / 322（67.7019%） | 104 | REQUEST 源图像 17.5；known，`stage2_person_0`，CONFIRMED |
| `af862980-c17c-4988-ae67-cf88c7cbacd5` | 49.76 / 49.784 | 430 / 431（99.7680%） | 1 | REQUEST 源图像 49.6；known，`stage2_person_0`，CONFIRMED |

两次任务分别由各自 REQUEST 框独立映射。映射到同一物理行人不构成跨重选任务的连续身份认证。

## 105 格如何产生

以下边界仅为可读性四舍五入，原 JSON 的浮点值不作修改。

| 源时间单元区间（s） | 未知格数 | 本场实际原因 |
| --- | ---: | --- |
| `[17.6, 17.7)` | 1 | `request_not_yet_confirmed`；单元开始时尚未确认，即使 17.6 图像匹配正确仍按原规则未知 |
| `[28.8, 31.1)` | 23 | 短遮挡及保护区：20 帧 `known_or_unresolved_external_occlusion`，3 帧 `no_fresh_selected_detection` |
| `[41.8, 49.7)` | 79 | 长遮挡、LOST 与等待重选：10 帧外遮挡保护未知，69 帧无新鲜被选目标检测 |
| `[49.7, 49.8)` | 1 | `task_boundary_within_time_cell`；49.76 新 REQUEST 落在单元内部，不能跨任务认证 |
| `[92.8, 92.852]` | 1 | `no_identity_evidence_in_time_cell`；末尾部分单元没有身份帧，保留分母 |
| **合计** | **105** | **30 外遮挡保护几何未知 + 72 无新鲜被选目标检测 + 3 边界/确认/末尾单元** |

对应原 `unknown_reason_counts` 为：
`request_not_yet_confirmed=1`、`unknown_identity_evidence_in_time_cell=102`、
`task_boundary_within_time_cell=1`、`no_identity_evidence_in_time_cell=1`。
诊断图像序列另有 **752 帧 = 650 CORRECT + 30 UNKNOWN_GEOMETRY + 72 NOT_OBSERVED**；
650/752 不能替代固定任务时间指标的 648/753。

## 未知是否来自缺 GT 或初始身份不明

**本场这两份小报告没有暴露此类原因。** 两任务完整 MOT 真值机会分别为 321/321、431/431，
缺真值机会均为 0；两次初始映射均 known，且选择得到独立框匹配佐证。
相机几何 926 次全部为 `FIXED_MOUNT`。
30 个几何未知全部是 `known_or_unresolved_external_occlusion`，对应既定快门请求前后
各 1 s 的保护规则，没有未决同类投影排序或初始映射未知原因。
另有 **22** 个正确帧使用 `unique_image_match_with_whole_mesh_front_certificate`，
其余 628 个正确帧为 `unique_unoccluded_image_match`。
不能删除快门保护，或把服务 ACK 当作精确渲染遮挡真值来改判这些未知。

72 个无新鲜检测帧实际分为：短快门 29.8–30.0 s 的 3 帧；
长快门请求区间内 42.8–45.8 s 的 31 帧；开闸后 45.9–49.6 s 的 38 帧。
这是缺少符合原规则的新鲜被选目标框，不等于日志丢包或已证明错误换人。
原安全报告记录长时丢失 43.46 s、悬停 43.452 s、明确重选 49.76 s，
无未请求的测量恢复、活动状态恢复或跟踪控制；重选后确认时间为 49.784 s。
这与第一版“长时丢失后悬停，等待明确重选，禁止自动认回”的定义一致。

## 结论范围

原 `stage2_evaluation.json` 的结果为 PASS，18 项 checks 均为 true；这只是该安全报告
声明的场景行为范围。它自身明确不认证物理身份、IDF1、HOTA、mAP 或三维精度。
本卡未检查该槽终态或导航结论，不能据此宣称 core12 PASS、全部身份问题已解决，
或对其他类别、种子及场景外推。

0 已知错误只说明已有独立证据的部分未观察到错误匹配；105 未知仍保留在分母中，
尤其不能用总体 86.06% 遮盖首次任务仅 67.70% 的证据覆盖。
稳定 track ID、UUID、预测及悬停状态均不能补作新鲜物理身份观测。

原始绑定（actual Humble53，不引用 Humble51 结果作证据）：

- `physical_identity.json` SHA256：`9e2b1405b42ae5e59d94c1ca3b2d35d480d145084f5482a0290f1a3cbc8e36c3`
- `stage2_evaluation.json` SHA256：`5a3628653027d5d50a6085fbc334f2e5afc0b2e2d642ad1ad4065d065743555b`
- 原身份评价版本：`whole_static_mesh_optical_z_front_v1`；原评价脚本 SHA256：`3a0b640a309ad811cc13687482bf6b0992fcc56c9a939bdccccaf5b9c1af57d8`
