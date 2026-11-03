# probe02 剩余五场的实际续跑

2026-11-03 18:00:37（北京时间），新 collector07 已实际调用原单槽入口，开始 `car_extension_latency_seed004`。Windows 原 monitor 持有 WSL 子进程，外层 launcher 持有 monitor 的原 Popen 并临时防止休眠；不自动重试、不覆盖旧实验。实际启动及心跳记录在 `results/diagnostics/humble54_pending_collector07_launcher01/`。

实时显示：[原进度页](../results/monitor_humble54_probe02_owner07/index.html)。该页报告进程、心跳、原始终态数和当前槽；实验通过率以真实终态为准。启动校验期间原生输出尚不存在，暂时显示无事件是正常的，不能据此判断路径错误。

本次原计划仍为 16 场。开始续跑时已有 11 场原始终态：7 PASS、3 FAIL、1 INCOMPLETE_EVIDENCE；后五场依次为汽车 latency、combined、speed_changes_velocity、speed_changes_position、far_distance。原来的 FAIL、null、INCOMPLETE 及原 owner06 退出码 2 均不改变。

注册源 SHA 为 `7d2523325bca8ef520fe0e5a7bd78da355943099e3f45efee2c3ad4e870cdd9b`，profile SHA 为 `c36f17363874173ee7fed08d482a68f518fd44cffd581d757de09ccd649ded55`，Windows launcher SHA 为 `3cfd98f01d6d9373aa01c45fd691ffd5a34e8dd1d3363edd12a990280322c923`。准备版实际 native check02 exit 0；注册差异只含三个源码字面及两个 profile 字段，原版本和回执已归档。执行入口还会重核完整冻结源与前 11 场证据。

汽车 dropout 的短窗未在原观察窗内恢复，故身份比较显式 null。新规则仅在已有明确丢失、明确无恢复、完整时钟/录包和原安全检查均满足时，将它记录为条件不可评价；原跟踪失败不变，不把身份未知计为身份成功，也不放行其他未知或物理身份准入。

同日 17:55:41—17:55:46，受控 ROS 消息关联 native03 已真实 exit 0：8 条单发送者消息得到 OBSERVED_CANDIDATE，16 条竞争发送者消息保持 UNKNOWN，真实清理完成。它只验证独立探针的受控关联能力，历史 strict 的 1,857 条 UNKNOWN 不改，完整管线及物理 E2E 仍未观测。

后续须先等原 owner 及其子进程真实结束，再用实际完整 16 场结果执行 28 条件空间测量、定标及完整 280 场预算。当前正式实验仍为 0/280；完整预算、final55 构建与正式准入尚未完成。若出现新故障或容量不足，保留原结果并解决实际问题，不能降低阈值、减少实验或宣称全部完成。

一次诊断更正：root 曾将启动时文件未生成和工具输出中的 JSON 转义误判为 UNC 错误。随后 root 与两个独立审查均按实际字符核实：路径均为两个起始反斜杠、段间单反斜杠，原页已正常读取。运行源码未修改，实验未重启；临时冗余只读 reader 已按创建身份核验后结束，原 monitor 和 WSL 子进程继续运行。

18:20:08，第 12 场 `car_extension_latency_seed004` 产生原始 PASS：距离 RMSE 0.741951 m，高度 RMSE 0.154516 m，真值覆盖率 1.0；原导航距离、高度、状态覆盖及末段稳定六项检查均为 true，无基础设施停止。终态原字节 SHA 为 `b2f1ec888c217cd1ac8e0dcfc56a19e4746dc5096e7902cf8c6d04c732330ab1`。原 collector 核验后继续第 13 场汽车 combined；此时累计 12/16：8 PASS、3 FAIL、1 INCOMPLETE_EVIDENCE。

同轮身份条件分类修复仅作用于 workspace 中的未来离线工具，运行中的 frozen54 和 collector07 源码均不改。38 项模块测试、9 项 runner 测试及独立的真实汽车小原件/4 项代表 fixture 复核通过。新 staging 候选也已准备并由 root 静审，仍保持生产关闭、未来输入未登记；它们不能替代真实完整 16 场、完整预算或正式实验。
