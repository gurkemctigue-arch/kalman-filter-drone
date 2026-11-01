# Humble43 扩展第五场失败快照

扩展16尚在执行。本快照形成时，前五场原槽与外层attempt均已闭合，4 PASS、1 FAIL，另11场尚未开始；正式实验仍为0/280。这里保存第五场的原小工件及随后形成的独立诊断，没有重新飞行、重评或修改失败记录。

`person_extension_combined_seed004` 原槽于2026-11-01 09:22:51.706659 UTC记录 `COMPLETED/FAIL`；flight退出0、infrastructure_stop=false。外层于09:23:21.491184 UTC闭合，error=null，原算法FAIL继续保留。完整扩展开发关口、容量、定标、最终登记和正式研究均未由本快照授予准入。

第一次FOLLOW为仿真18.4秒；系统在34.86秒已经LOST，早于43.4秒开始的预设长遮挡。原跟随评价中短遮挡PASS，长遮挡因 `prediction_observed=false` 判FAIL；不能把先前丢失延续到遮挡窗口解释为长遮挡独立触发了失锁。50.4秒真实显式重选、50.404秒新UUID测量确认后，持续跟踪43.164秒的原检查PASS。

外层还保留 `navigation:REGISTERED_PERFORMANCE_GATES_FAILED`。全程base_link距离RMSE为2.451894米、绝对误差p95为6.488093米，高度RMSE为0.170694米；真值为752/752。距离、高度末端均稳定，不代表全程达标。提前失锁的直接触发是状态年龄超过0.75秒，目前没有充分证据将根因归为检测、关联、延迟或观测门控中的某一项。

[早期观察](evidence/humble43_combined_early_loss_observation01.json)明确不是终态评价；[闭合诊断](evidence/humble43_combined_early_loss_closed_binding01.json)绑定原槽、报告和外层回执。后者的14项小元数据一致性检查不计作新增飞行或算法测试；telemetry哈希引用原槽保存值，本次归档没有重新读取telemetry或bag。

`ARCHIVE_MANIFEST.json`列出原来源、字节数及SHA256；`SHA256SUMS`覆盖payload、说明与manifest，排除自身。复制的JSON保持原字节和原绝对路径；完整底层录包仍在本机，GitHub快照不能独立替代它们。此前的失败、未知样本和历史结果保留。
