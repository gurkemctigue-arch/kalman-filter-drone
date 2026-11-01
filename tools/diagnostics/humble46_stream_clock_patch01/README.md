# Humble46 时钟保护修复：最小证据快照

本目录保存 Windows 定向测试、独立代码审阅，以及 Humble45 第二场中止的原生导出回执和两份分析。复制文件保持原始字节、换行和内嵌 POSIX 路径；`manifest.json` 逐项绑定原件和副本，`SHA256SUMS` 校验本目录全部其余文件。

当前边界：**Humble46 尚未进行原生构建或飞行验证。** 这里的 PASS 仅表示相应 Windows 测试与独立静态审阅通过，不表示核心十二场、安全四场或正式实验已验收。

## 实际验证

- `windows_tests/`：04 批次实际运行 145 项测试，全部通过、0 项跳过。随后只在新登记和校验器中加入 `status_wall_check_clock` 覆盖字段；05 批次针对受影响的时钟及登记绑定运行 22 项测试，全部通过、0 项跳过。两份回执分别保存测试前后的七个源码 SHA256，均未在测试期间变化；最终源码均为 UTF-8 LF。
- `independent/`：最终独立审阅通过，覆盖最终七个文件、04/05 原始日志、保护状态和新旧协议边界。审阅者没有执行测试、原生构建或飞行。
- `native45/`：保存原生元数据核查、单次原生导出回执、原 invocation，以及两份独立分析。导出窗口为源时间 56.0–60.64 s，仅请求精确 60.2 s RGB-D 帧；未反序列化 GT。原生导出完成仅证明该次导出的完整性。

Humble45 原失败保持不变：第二场 `person_stage1_position_seed004` 为 `INFRASTRUCTURE_ERROR`、工程 `FAIL`；原核心终态为 1 PASS、1 INFRASTRUCTURE_ERROR、10 PENDING，失败 owner 及原退出状态均保留。原中止快照的里程计接收年龄约为 0.733 墙钟秒，源年龄为 0.080 秒。导出中的 command 记录时间不能替代 supervisor 本地回调接收时间；原始 FMU 和 adapter timing 未在此次通用导出中解码，因此两份分析均未排除上游、适配器或调度故障。

## 修复语义与后续验证

新 `source_sim` 模式直接读取实际 ROS header 计算源年龄：里程计和 command 各自保留 0.5 s 源龄及 0.05 s 未来界。请求 RTF 只用于预先登记接收停流的墙钟预算 `0.5 / RTF`，上限为 10 s；RTF 0.125 对应 4 s，RTF 1 对应 0.5 s。超上限直接拒绝，不截断预算，也不按 RTF 换算观测年龄。

无效源戳、重复、未来或回退消息不刷新已接受的接收时间；时钟回退锁存至重启。合法源戳的 `valid=False` command 仍立即表达停止意图；即使停止消息的 header 被拒绝，也禁止继续转发旧运动命令，直到收到后续合法有效命令。command 过期或停发维持 HOLD。0.1 s 稳态 watchdog 只在 FOLLOW/HOLD 复用原完整状态保护：里程计、状态源龄/墙钟/未来界、failsafe、解锁和 Offboard 条件；只在中止时发布一次无效命令，不增加正常 20 Hz 发布流。它与控制共享单线程 executor，不能证明独立 DDS 活性。

node 默认仍为 `receipt_wall`，旧自定义 command timeout 的两道原有门保持不变。trial CLI 未给 stream mode 时，按显式 PX4 时间域解析：`source_sim` 对应新模式，`receipt` 对应 `receipt_wall`，并在 `run_config` 保存解析后的实际模式和预算。新核心协议显式指定新模式；缺少新登记的历史协议由当前 runner 显式请求 `receipt_wall`。原冻结脚本和历史档案不作追认或改写。新 stream 登记中的 `status_wall_check_clock` 明确覆盖 FOLLOW/HOLD 下旧状态时钟描述；状态的 1 s 源龄、10 s 墙钟、0.05 s 未来界未改变。

原 external safety4 argv 已显式使用 PX4 `source_sim`，因此可通过同源 CLI 默认解析采用新策略；原 strict 工具和 canonical 没有修改。不过其旧校验仅覆盖原有字段，后续必须额外绑定最终候选源码及默认解析规则，并逐一审阅四场实际 `run_config` / runtime YAML 中的模式、源龄、未来界、接收预算、请求 RTF、`simulation_only` 和 `use_sim_time`。本目录没有这四场的新运行证据，也没有安全验收结论。

## 未复制的原生载荷

原生 manifest 仅在本目录 manifest 中登记其原路径、字节数和 SHA256，不复制 769442 字节 manifest，也不复制导出的 5396 个载荷文件、bag、CDR、图像或 telemetry。分析与导出回执中的外部路径保持原样，完整原件仍留在 `D:/WSL/UAVHumble22-validation`。
