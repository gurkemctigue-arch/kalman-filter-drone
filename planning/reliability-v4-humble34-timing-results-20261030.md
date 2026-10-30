# Humble34 单场 75 秒计时诊断（非可靠性验收）

截至 2026-10-30 18:36 UTC（北京时间次日 02:36），原始 `person_stage1_velocity_seed004` 已完成，槽位 `PASS`、`execution_status=COMPLETED`、`infrastructure_stop=false`。这是一场独立计时诊断，不替代 Humble32 的失败试验，也不代表阶段一至三或正式实验全部完成。

冻结来源提交为 `b8107f6080915c6e2a57187b5a8dce8333a4db45`，602 个源文件的 canonical SHA256 为 `6dd0331492e3b95476e217e0fb9054c206297c621f17c2f90b649bd9f0172dd5`。本次来源承接计时插桩并修正 Python 3.10 测试兼容，没有可靠性算法变更。四包冷构建、真实消息 CDR、FastCDR、模块/ament 隔离通过；完整 Ubuntu 验证 1543 项中 1538 通过、原 5 项平台跳过。Humble33 的原 4 项测试错误与 FAIL 记录保留。

首次 `plan01` 入口在创建计划和起飞前被原环境检查拒绝：导入 detector 时 OpenCV 在 `LD_LIBRARY_PATH` 前插自己的库目录。外部入口现先检查原环境，再在模块导入的 `finally` 中精确恢复原 LD 字符串；后续原检查及 Agent command/ldd 检查保持。修复只涉及外部工具，不改冻结源、原授权或失败记录；独审及实际 Linux 28 项隔离测试通过。新 `plan02` 成功创建唯一 PENDING 槽，随后只执行一次原始试验。

## 原始评价与完整分母

注册 FOLLOW 为 75 秒；独立评价保留归档尾部，区间为 source 18.0～93.3 秒，共 754 个固定 10 Hz 时间格。

| 评价 | 原始结果 |
|---|---|
| PX4 source clock | `PASS` |
| Native startup | `PASS` |
| Surface flight acceptance | `PASS` |
| Navigation 顶层状态 | `RECORDED_WITH_CENSORED_FAILURES` |
| 槽位工程门 | `PASS`；原距离、高度、覆盖率及最终稳定门均通过 |

全区间 base_link 距离 RMSE 为 **0.753833846 m**，高度 RMSE 为 **0.159340942 m**；有效导航覆盖率 **691/754 = 0.916445623**，物理跟随真值覆盖率为 **1.0**，距离和高度最终均 settled。原 **63/754 LOST／未控制时间格**完整保留，不能将 navigation 顶层状态改写为 PASS。有效状态样本中的 KF 位置 RMSE 为 0.308780431 m，速度 RMSE 为 0.057880141 m/s；这些数值不补齐丢失时间格。

计划长遮挡后，HOVER 首次为 43.752 秒、LOST 首次为 43.76 秒；50.0 秒显式重选，50.028 秒确认，随后持续跟踪至归档末端，原 0.75 秒保护门保持。短遮挡评价亦通过。外层于 18:32:48.973503 UTC 正常结束，returncode=0、final_errors 为空、残留进程为空；独立观察器正常退出，602 文件来源绑定前后相同。

## 计时观察

`ros.log` 中 929 条计时记录全部可解码、全部 completed，无重复 job key 或坏记录。下表均为墙钟毫秒；不将 source 秒与墙钟相减或按 RTF 换算。

| 计时范围 | p50 / p95 / max（ms） |
|---|---|
| Worker 工作至计时日志前 | 22.014 / 25.122 / 1523.199 |
| YOLO predict | 19.382 / 22.140 / 1508.079 |
| Decode | 0.459 / 0.712 / 2.100 |
| Depth/navigation geometry | 1.097 / 1.296 / 12.218 |

唯一 ≥0.5 秒的样本是**首条 job**，acquisition=0.1 秒、submit=0.12 秒，工作墙钟 1.523199301 秒，其中 YOLO 1.508079318 秒；FOLLOW 从 18.0 秒才开始。FOLLOW 开始后含归档尾部共有 753 条 job，最大工作墙钟仅 0.063813447 秒（acquisition=68.7 秒）。首条慢样本不能单独证明 warmup、调度或其他内部成因。

旧失效附近 source 84.8～86.2 秒的 15 条 job 最大墙钟 0.025082027 秒，采集时间间隔最大 0.1 秒；同窗记录的 tracks 只有 tracking/coasting，没有 LOST。本次**未复现 Humble32 后段原失效链**，不能据此宣布修复成功。原 Humble32 核心仍为 **9 PASS / 3 FAIL**，正式试验仍为 **0/280**。

逐帧发布相关分段只有 754 条已知、175 条缺段保留 UNKNOWN，不置零。inclusive 锁持有时间不再加到排他的 stage 合计；thread CPU 仅覆盖调用 worker 线程，不是所有 native worker。日志未提供观测交付／状态的完整关联证据，E2E 延迟继续 UNKNOWN；本次不提供因果结论或完整开发验收。

## 原录制离线输入

Humble32 汽车 crossing 原录制的有限输入提取已实际 PASS，用时 23.520471 秒：保留 145 个原始 atomic frame，导出 29.7～32.5 秒窗口中 27 组 exact depth/CameraInfo NPZ。原归档与关键源哈希前后不变，owned 临时缓存已清理；未重跑检测或仿真，不使用 GT。该数据供 baseline 重放开发，尚无反事实重放通过或新闭环改善结论。导出中传感器记录后附，消费端须按 `source_filtered_index` 恢复原记录顺序；tracks 的 `output_s` 不是完整的实际发布时间证据。

## 本地证据路径与 SHA256

以下简称 R=`D:\基于yolo和卡尔曼滤波\results\frozen_fullplan_v4_humble34`，M=`R\reliability_v4_timing_person01_seed004_matrix`，T=`R\reliability_v4_timing_person01_person_stage1_velocity_seed004`；R/M/T 均为本机目录，未作为 GitHub 大文件上传。

| 本地文件 | SHA256 |
|---|---|
| `R\freeze_validation\build_validation_summary.json` | `b8e6e6b354db884a90338cfe2190b120e108c3e4f572fa643bcbcecfd9a93e41` |
| `R\freeze_validation\timing_plan_driver01\execution_terminal.json` | `e5a8c95041e1f104d09d7ab8663160ac0613c8eb8fdcc52809937899e9ebbe19` |
| `M\timing_driver01\execution_terminal.json` | `93ee9d0a9c4f5dc1f297672aeffdb972f361e1e6948ed1a12315647e2874bad7` |
| `M\slots\person_stage1_velocity_seed004.json` | `6c9af61a25275f1f3e19045d6562c2636eb2cbc2ed69a85f039449b8703d0e85` |
| `M\timing_driver01\timing_log_analysis.json` | `6b6fc244194c1dcbc653207d1a3739434d9928a6d694bcf3795395b2ff537778` |
| `T\ros.log` | `ca0d296f2bed1fe9368572368747e84bad818a39ad99969b5f9053812f88695a` |
| `T\px4_source_clock_report.json` | `80010bfa595a76136287e57b2448972faf6840ed1bb66b3b86e56354866ee8ea` |
| `T\native_startup_report.json` | `84376c3e499cb38bbda56185296a18bcea12667422df99492e92eda848199f39` |
| `T\flight_evaluation.json` | `b5c053956ce7658f082d2045786f4be56a602af220c83a59638f3e308343a07a` |
| `T\navigation_reference_evaluation.json` | `a2e50b1500df27d0eb6cd25c962fc0f18ee968962bb426377f6518d0afbf8b0b` |
| `D:\WSL\UAVHumble22-validation\humble32_counterfactual_inputs01\receipt.json` | `0585b28e6d4f7911ad56696e77aefc37fcf0e79edcd26301d251dfbf4955d868` |

slot 绑定的 summary、四份评价、ros.log、telemetry、recording_closure、bag_integrity、process_exit_codes 共十项闭档工件哈希已只读复核一致；未重新打开 bag、重跑评价或修改原结果。
