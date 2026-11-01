# Humble43主机待机与计时差异派生快照

本目录于2026-11-01 11:28 UTC整理已有诊断，只摘录允许公开的事件元数据、原计时比较和新辅助进程文件。它不是新事件查询、飞行、测试或研究验收。原Windows事件XML和完整诊断留在本机，未复制到此目录。

原诊断：`D:/WSL/UAVHumble22-validation/humble43_modern_standby_clock_gap_independent01.json`，51,979字节，SHA256 `2d568768ec5790567372b89973ff7fb5f4cd9d4b6bf4b24329a1cc95e275dacd`。[派生摘要](modern_standby_derived_summary01.json)为8,803字节，SHA256 `e54f1d2e562a5d73c43e61c0b835460d5b6096cb68b8a48cd7c45f991f11c7b6`；其中10条事件只保留UTC、ID、RecordId、Reason、SleepEntered和duration。以下两条明确报告实际睡眠：

| 退出事件UTC | ID / RecordId | Reason原值 | SleepEntered | 实际睡眠秒数 |
| --- | --- | --- | --- | ---: |
| 08:33:03.3760783Z | 507 / 848770 | Lid | true | 2715.306845 |
| 11:11:34.3053212Z | 507 / 848828 | Lid | true | 903.207217 |

第三槽导航命令原UTC跨度为2832.642921秒，原monotonic耗时为117.6539923秒，差2714.9889287秒。848770退出事件位于该命令内，报告的睡眠时长与此差值仅差0.3179163秒，强支持主机Modern Standby挂起是该间隙的主要解释。约0.318秒余差仍保留，旧窗口未包含同次睡眠的进入事件，不补造进入时间。整槽约69分钟UTC跨度不能全部记作算法耗时，也不改写原工程结果或计时。

后续903.207217秒实际睡眠同样披露；不能把506进入事件至507退出事件的整个会话跨度当作实际CPU睡眠时长。其余SleepEntered=false、duration=0的退出事件仍在派生摘要中，不能把每次506/507都计为实际睡眠。Reason是操作系统报告的原因，不识别操作者，不据此归责用户。

08:40:36 UTC对07:40—08:40 UTC的旧限定查询，针对Kernel-Power 42/107、Power-Troubleshooter 1及Kernel-General 1均无匹配，这一真实历史结果保留。它未查询506/507，不能用来排除Modern Standby；本次摘要沿用后续已保存的506/507证据，不重复查询系统事件。

下列四个文件是新helper来源的逐字节副本；CRLF等原字节保留。status另行命名为一次观察快照，不充当持续更新的状态文件：

| 文件 | 字节 | 含义 |
| --- | ---: | --- |
| [keep_project_awake_display01.ps1](keep_project_awake_display01.ps1) | 2444 | 新任务辅助脚本 |
| [display lease](keep_project_awake_humble43_display_lease01.json) | 659 | 到期2026-11-08 05:52:27.433025 UTC，沿用既有期限 |
| [display process](keep_project_awake_humble43_display_process01.json) | 717 | PID10468、创建时间和脚本哈希绑定 |
| [display status观察01](keep_project_awake_humble43_display_status_observed01.json) | 651 | 11:27:37.3659442 UTC，ACTIVE、API接受 |

新请求为线程级`0x80000003`（CONTINUOUS、SYSTEM_REQUIRED、DISPLAY_REQUIRED），没有修改全局电源配置。API接受只证明该请求被接受，不能证明防止所有睡眠、覆盖显式睡眠/合盖策略或保证后续连续运行。脚本具备release信号、租约消失/到期退出及finally释放路径；本次归档没有实际触发释放。RELEASED记录中的`requested_flags`描述初始唤醒请求，实际finally释放调用参数是`0x80000000`。

旧870字节脚本和原leases只读取，不复制或修改；本次归档前后哈希一致，具体哈希及四份新副本的完整哈希见派生摘要。原诊断、旧失败、未知样本及全部计时保持原样，不增加研究PASS结论，也不证明整个扩展批次或正式准入完成。

[SHA256SUMS](SHA256SUMS)校验本说明、派生摘要和四份helper副本，排除校验表自身。
