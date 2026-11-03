# 容量复核准备说明

当前实际路径与状态：原 7 步测量窗口为 `/mnt/d/WSL/UAVHumble22-validation/humble54_probe02_closed_measurement_after07_01/terminal.json`；f32 续接的 6 步窗口为其同级 `humble54_probe02_closed_measurement_after07_01_continue_after28_01/terminal.json`。前者因 `Refused: Refusing large input` 停止；后者 6 个实际命令均退出 0，整体仅因最后的容量门拒绝而退出 2。原完整预算位于 `results/frozen_fullplan_v4_humble54/full280_storage_budget_probe02_after07_01/budget.json`，其约 153 GiB 物理缺口尚未解除。

新工具已完成代码、22 项作者合成测试和独立审查，**只准备、未原生执行**；新源码固定为 `a67a90f7786a1c8e918cd8953d2447f77d0667cb74404d44813917daf3534002`。必须在真实容量发生改善后，再由主代理显式运行容量复核。不能套用旧设计卡的“单一 12 步成功窗口”。只有产生真实新正预算后，才进入后续 staging 消费适配；该适配目前尚未实现，工具成功不会自动启动它。

这里只准备了 `../refresh_capacity_after28.py` 和 Windows 合成验证。准备完成、测试通过或独立审查通过，都不表示原生容量复核已经执行，也不表示正式实验可以启动。

本工具适用的是已经真实发生的两个窗口：

1. 原测量窗口完成 7 个实际命令，因 `Refused: Refusing large input` 停止，整体退出码为 2。
2. 固定 SHA 为 `f32bd4bc97e58a15417fb9757eceb7e7cf2de2cb4e16ac5df54d200a40bae3b0` 的续接代码完成 6 个实际命令，随后仅因完整 280 槽物理容量不足停止，整体退出码仍为 2。

不能把这两次运行描述为“原测量 12 步全部成功”。早先容量设计卡中的单一 12 步窗口前提不适用于此次真实记录。本工具没有修改原测量代码、其执行归档、原终态、原负预算、原产物或原容量规则。

工具重新核对原收集闭合、两个终态和原 28 份测量及 690 个输入声明，并复核续接终态的 1107 项输入绑定。原 R0、两次具名导出及其来源保持不变；只对 R0 已认证的两个数组和六个侧文件做限定路径的流式哈希。该独立读取器每个文件最多允许 16 MiB，读取前检查大小，读取中最多多读一个检测增长的字节，前后核对文件状态并验证原 SHA；它不重新导出、不计算校准、不读取 bag 或模型。原小文件读取规则和两个固定身份 JSON 的例外保持原样。

没有参数时只打印说明，不加载辅助代码、读取实验输入或启动子进程。实际执行必须由项目主代理在 `UAVHumble22` 内显式调用，并提供已独立审查的当前脚本 SHA 和一个尚不存在的外部 receipt 目录。该目录必须是原验证目录下的新直接子目录；工具在其中写入新的 inventory、budget、日志和终态。这里不预登记未来路径、未来 SHA 或未来结果。

命令格式如下，尖括号内容必须由主代理在实际执行时填写；不能原样执行：

```text
python3 /mnt/d/<实际项目目录>/tools/experiment_orchestration/humble54_closed_measurement01/refresh_capacity_after28.py --execute --reviewed-source-sha256 <独立审查确认的当前源码SHA> --receipt <验证目录下尚不存在的新receipt绝对路径>
```

持有原机器锁并通过原 blocker 检查后，实际命令只有：原生 idle 查询、原工厂的 `physical_inventory`、原工厂的 `full280_budget`。不建立 owner、触发器或自动重试链。

新旧 `storage` 对象和 `storage_sha256` 必须完全相同，28 个单元、280 槽、1.15 增长系数、临时峰值、五类交付预留和其他预留均不能减少。除采样时间、新 inventory 引用和真实当前容量外，预算来源也必须保持一致。再次负预算、未知值、任一漂移、输出冲突、中断或命令失败都会停止；已经生成的本次输出保留。正预算仅表示此次容量复核通过，不代表 admission、算法验收或飞行验收。本工具不包含 staging 适配器。

合成测试使用临时目录、小 JSON 和显式 fake child；验证正预算、负预算留痕、旧文件不变、来源或数组漂移、输出冲突、未知容量和两个窗口的严格边界。独立审查和测试记录另存于本目录，均应注明没有原生执行。
