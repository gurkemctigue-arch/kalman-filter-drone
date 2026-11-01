# Humble42之后的支持门控修复与新验证

更新入口：2026-11-01 13:46:07（北京时间），下述修复已进入Humble43隔离来源，同源核心12独审通过，见[原收据](../tools/experiment_orchestration/humble43_core12_closure_snapshot01/humble43_core12_closed_independent01.json)；原生v2组件04的85项全PASS、0跳过及3项describe核验真实完成，见[组件快照](../tools/experiment_orchestration/humble43_native_v2_components04_snapshot01/README.md)。安全4原四场全部PASS、完整原guard及闭合独审PASS，原主命令于05:16:58.567204 UTC退出0，见[安全闭合快照](../tools/experiment_orchestration/humble43_safety4_closure_snapshot01/README.md)；postwait owner COMPLETE与较早COPY候选pending属于不同阶段。扩展原plan已退出0并通过104项静态独审，独立FINAL合同已发布；原16场run于05:46:07 UTC启动，当前首飞前核验、0/16完成，见[扩展启动快照](../tools/experiment_orchestration/humble43_extension16_start_snapshot01/README.md)及[扩展进度页](../results/project_progress/humble43_extension01/index.html)，不把启动当作已起飞。正式仍0/280，实际扩展、容量/定标及正式准入仍待完成，不能称全部验收通过。最新证据见[本轮验证记录](reliability-v4-humble43-validation-20261101.md)。以下保留修复提出时的原始计划和当时边界。

2026-11-01。本文件记录已进入工作区、尚未新冻结或飞行的修改。原Humble42保持8 PASS、1 FAIL、3 PENDING，正式0/280。

原生录包导出及[因果分析](../tools/diagnostics/humble42_native_causal_snapshot01/humble42_core09_native_causal_analysis01.md)证实：30.7秒仅有的候选没有可靠表面支持，却初始化了track4；这条轨迹最后接受于31.3秒，随后与选定track3竞争同一候选。track3最后接受于31.6秒，32.36秒测量年龄0.76秒触发LOST。原记录不足以确定track4的物理身份，不能把它直接称为已证明的重复车辆。

工作区补丁只约束自动新生：在hybrid_3d、拒绝歧义关联、且表面恢复明确启用时，尚未匹配且缺乏表面支持的候选，即使没有同帧重叠锚点，也暂缓建立轨迹。候选继续参与原关联图和唯一实例候选计数；既存轨迹更新、显式框选、原重叠两帧确认、时效和距离/马氏门控均沿用原规则。后续获得支持的观测可以进入原出生流程。

这一限制可能延迟真实新目标的初始化；支持标志也不构成物理身份真值。它不能自动消除31.5秒的一轨迹多候选歧义，亦不证明新飞行一定通过。验证必须保留这些代价，禁止以少建立轨迹作为身份正确率的替代。

同时新增`uav_tracking.stop_observer`，由实际runner委托记录每次停止信号、创建身份、wait时限和原生退出码。ROS初次仅给launch主进程SIGINT，其余进程给原进程组；原停止顺序及8/5/3秒预算不变。事件与总结分开保存，总结只在完整写入和fsync后排他发布。观测完整只表示日志完整，原进程健康检查仍决定退出是否合格。

当前验证：出生相关76项Windows行为测试通过，额外8项独立边界通过；runner相关10项及最终日志发布5项通过。退出helper与已独审版本字节一致，外部27项观测夹具覆盖另一个范围。它们均不代替Linux构建、实际飞行或退出验收。

下一步按依赖执行：

1. 完成实际源码差异独审、提交，并为全新Humble43根生成来源清单。42的健康构建可作为源码前驱；原停止批次和失败owner必须作为原值归档，不能冒用41或伪造成功终态。
2. 新根完成四包构建、模块/ament来源、消息序列化与完整Linux测试；实际导入检查纳入新增`uav_tracking.stop_observer`。
3. 以新名称进行一次原参数汽车交叉诊断。核对新生延期、所选身份、短遮挡、长遮挡进入预测/丢失悬停、显式重选和后续连续跟随，同时核对全部启动/停止进程及信号日志。不得复用原槽或放宽门限。
4. 若该诊断通过，在同一来源重新运行全部核心12，再进入安全4、扩展16、容量与定标。若失败，依据新证据继续修复，保留所有尝试。
5. 最终来源及登记齐备后才运行正式120+160，以及四法离线比较、检测/身份统计、视频图表和最终Word/PDF。正式数量不由开发诊断累计。

完整仿真后的Gazebo退出根因仍未知。一次最小RGB-D退出已通过，但新补丁是观测措施，不能称为原退出故障已修复。
