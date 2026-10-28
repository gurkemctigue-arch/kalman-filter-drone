# V4 条件扩展的冻结与证据约束

当前扩展协议仍为 `DRAFT_NOT_FROZEN_NOT_EXECUTED`，没有正式结果。核心工程矩阵保持两类×六组×十种子=120槽；噪声、深度空洞、掉帧、延迟、组合故障、速度/位置控制加减速、远距离构成独立两类×八条件×十种子=160槽。历史失败、缺失和核心参考槽不能作为额外成功槽计入扩展。

`scripts/run_reliability_v4.py plan --probe --extensions` 可产生开发计划。默认覆盖两类和八条件，必须使用1000–1009以外的开发种子。`--conditions`、`--classes`可缩小开发诊断范围，但正式登记的开发readiness须覆盖全部16个类别/条件格。核心和扩展共用机器锁、不可覆盖计划/工件、一次尝试和基础设施停止后的诊断规则。

扩展开发readiness检查可运行、可评价及原安全保护，不以压力条件下的算法全PASS筛选工况。它要求相同最终飞行源、权重、runtime和独立评价源码；实际完成的开发计划、终态record、报告、归档配置和文件SHA；独立源时钟/帧连续性与原生起飞PASS；完整录包/诊断；长丢失时悬停、持续低速、重新选择前禁止恢复任务/跟随。导航性能FAIL、短遮挡丢失或恢复失败等已知算法边界须逐槽原样写入 `known_algorithm_failures`，不能删槽、改为成功或放宽阈值。核心12格开发门仍要求独立工程验收PASS。

登记JSON的 `development_readiness` 是 `{"path":实际gate文件,"sha256":实际文件SHA,"evidence":实际gate内容}`。gate采用schema2，包含 `result:"PASS"`、`ready_for_formal_condition_extensions:true`、源码/权重/runtime/导航阈值 `bindings`、全部开发 `probe_slots` 和精确 `known_algorithm_failures`。命名checks必须覆盖 `EXTENSION_PROBE_CHECKS`；布尔值不能代替实际报告验证。开发record结束时间须早于明确UTC的 `registration_utc`。当前仓库没有此正式readiness证据，不能仅把status改为REGISTERED。

当工作树存在扩展协议时，新核心FORMAL计划必须先验证并绑定已登记扩展协议的完整内容和文件SHA。因此扩展条件须在第一条核心留出飞行前冻结，不能看到核心结果后补登记。旧的、不含扩展协议文件的历史计划接口保留兼容性。

扩展FORMAL计划额外必须传 `--reference-plan CORE_PLAN_JSON`。该参数必须指向实际冻结的核心FORMAL计划；扩展绑定该文件SHA、plan摘要和全部40个clean参考ID，核对相同飞行源、权重、runtime、核心协议及同一扩展登记。每个扩展槽预先固定同类别、同种子参考：位置控制加减速配 `stage1_position`，其余配 `stage1_velocity`。所有实际核心开飞UTC也必须晚于扩展登记。原核心计划改变、登记改变、来源不同或参考槽缺失均拒绝执行。

正式扩展只能使用完整两类×八条件×1000–1009的160槽。与核心参考进行配对统计时保留每条件十对的完整分母和实际有限配对数，公开FAIL/INTERRUPTED/缺失，不能把图像帧当作独立重复。远距离改变物理设定值，须明确这一变化，不声称相同相机视角或图像输入。
