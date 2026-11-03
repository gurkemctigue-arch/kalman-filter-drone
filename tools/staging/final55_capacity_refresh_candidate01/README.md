# 容量复核窗口的 staging 隔离候选

状态：**已实现候选，默认关闭生产，尚未原生执行**。当前没有真实正预算，未登记任何未来成功终态或预算。现有容量约 153 GiB 的缺口不因该候选或合成测试而消失。

最终候选源码 SHA 为 `c83cc666cdf8924f53033446c075d284eeccaafe5f9cbd95fb9253d8262f8e12`；10 项作者测试和 43 项独立检查通过，最终独审见 `independent_review02.json`。**不得直接 execute**：必须先有真实容量改善与真实成功的容量复核原件；未来实际 pins、输出登记和生产启用由 root 完成，登记前还须再次源码审查。旧独审 01 保留历史，不是当前源码依据。

`stage_after_refresh.py` 接收未来真实容量复核的终态与正预算，用于准备源代码 staging。它保持原 7 步 `Refused: Refusing large input` 失败、f32 续接 6 个命令退出 0 后仅容量拒绝的失败，以及未来容量复核 3 步成功这三个独立窗口；不会制造“单一 12 步成功测量”。staging 指源代码准备，不代表冷构建、飞行或正式 admission。

旧 `tools/staging/final55_after07_stage01/stage_after07.py` 的 `validate_terminal()` 要求完整成功 12 步，`run_registered()` 又要求预算在旧原址、旧窗口内产生。新候选单独处理这些不适用的消费约束，**没有修改旧代码或旧证据**。

实现复用的内容包括：

- 固定 f32 与容量复核工具的只读验证函数，重新核对原 full16 闭合、原 7 步失败、28 份测量和 690 个声明、原 6 步窗口及其全部输入、R0 和两个具名导出的 8 个派生 JSON。
- 严格核对未来真实的 idle、inventory、budget 三个命令及其顺序、argv、整数退出码、进程身份、日志位置和 UTC。原失败窗口、旧负预算、R0、派生文件和输入家族必须与复核结果一致。
- 原负预算必须仍只因已知物理容量不足拒绝。新旧 `storage` 和摘要完全相同，其他预算来源只允许新 inventory 的对应引用变化。新预算仍须通过原 `positive_budget()`；负值、未知值或其他合同变动均拒绝。
- 原 `candidate_inputs()`、10 个 overlay、原 profile 和 contract、`base.prepare()` 及 `prior.execute_with_outcome()`。派生 JSON 和全部小输入在 prepare 前后、staging 执行后都要再检查，发生漂移时保留真实失败输出。

当前 `PRODUCTION_ENABLED=False`、`REGISTERED_INPUTS={}`。无参数只打印说明；显式 `--preflight` 或 `--execute` 在未登记时都拒绝，不加载辅助代码或创建输出。未来由 root 核对真实产物后完成生产登记及再次审查；只有两个实际登记角色：`capacity_refresh_terminal`、`capacity_refresh_budget`。路径须指向已有外部复核 receipt 的精确 `terminal.json` 和 `budget.json`；原历史绑定与容量复核源码使用现有固定 pins。

未来 stage/receipt 输出目录由 root 显式传入，不能复用已经存在的目录。它们及 admission/outcome 侧文件必须彼此独立，原始路径和解析后路径都不能进入原 7 步、原 6 步、新容量复核 receipt 或其他复用证据、工具、校准和预算目录，也不能成为这些目录的祖先。候选还要求当前源码的准确审查 SHA；不存在命令行启用生产、启动 WSL、建立 owner、自动续接或重试的入口。

预算是采样时刻的容量快照。候选记录其真实年龄，并明确写入 `capacity_currently_revalidated=False`，不宣称当前空间仍足够。原合同没有 TTL，本候选没有新增任意过期秒数。正式实验之前和每一槽的当前容量检查仍属于原 guard；本候选不会代替这些检查。

测试仅使用临时目录、小 JSON、明确的 fake prepare/execute 和原始小源码。临时 fixture 中的正预算不属于真实实验产物，不能用于实际登记。未读取真实 bag、模型或派生数组，未修改冻结源，未执行 native/WSL 或 Git 提交。
