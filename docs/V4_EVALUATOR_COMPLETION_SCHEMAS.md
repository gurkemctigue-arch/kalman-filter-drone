# 离线报告完成状态与工程验收

Humble12的开发首槽`person_stage1_velocity_seed004`真实飞行退出0，独立source/native/surface报告通过，导航真值457/457，但旧`research_failures.py`只查`acceptance.result`及顶层`result`。三个实际使用`evaluation_status`的已完成报告因此被误判不存在，原运行器正确停在INFRASTRUCTURE_ERROR并保留其余11个PENDING。

修复后的离线分类器明确识别已命名的schema-v1 source/native/navigation/physical-identity报告，检查版本、报告来源形状、所属trial及PASS标志/原生起飞checks的一致性。它保留legacy surface的`acceptance.result`和stage2/gimbal的`result`形态。未知文件形态、未知状态、缺字段、矛盾标志、非预期退出码、缺包、traceback及崩溃继续停止。

`RECORDED_WITH_CENSORED_FAILURES`与`RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS`只表明报告已计算完成，不表示算法通过。导航的删失/丢失和身份未知区间仍保留，最终PASS由独立工程门判定。合法的INCOMPLETE报告同样只说明计算明确结束，不能提升为通过。

`rg`核查显示该分类器只由试验/guarded研究运行器在飞行后调用，`ros2_ws/src`及便携在线控制/估计未导入它。因此已将其在`run_reliability_v4.py`的OFFLINE_HELPERS中显式登记；正式文件仍纳入完整source hash，只有飞行算法来源比较与离线来源比较分开。

原Humble12计划、终态、报告和哈希均不改。诊断及弃用原因另存于其matrix的`diagnostics`和`ABANDONED_DEVELOPMENT_PLAN_REASON.json`。新Humble13的完整开发计划在运行前重新命名、冻结；Humble12录包不替代Humble13预先选定的两类stage1_velocity seed004标定数据，正式种子1000–1009未被使用。
