# 冻结 166 次飞行的失败分类扩展说明

工具：[summarize_full_plan_failure_taxonomy.py](../scripts/summarize_full_plan_failure_taxonomy.py)。它只读取现有小型 JSON，既不启动飞行，也不读取 bag、telemetry、视频或执行评价/重试，不修改冻结计划、正式台账、分类器、安全门控或补充实验代码。

## 完整运行

等所有 166 个原计划槽位终止后，在项目根目录执行：

```powershell
python scripts/summarize_full_plan_failure_taxonomy.py --root results/frozen_fullplan_v3 --output results/full_plan_failure_taxonomy_v3_166
```

输出必须是不存在的新目录。默认发现任何 PENDING 或运行中的槽位就拒绝写最终结果，不会持续轮询，也不会触发补跑。只有严格匹配冻结计划的 166 个唯一槽位全部处于 PASS、FAIL、INCOMPLETE 或 INTERRUPTED 等终止状态时，才标记 `is_final166=true`。这个标记只表示终止记录齐全，不表示全部通过、证据完备或研究目标已经完成。

工具复用已完成的阶段一 100 次独立分类，并验证其两份原始汇总仍与先前 SHA 相同；阶段二、三按冻结的 66 个槽位，直接读取对应的原生评价 JSON 和原 manifest。三阶段名称集合必须与冻结 plan 一致。

本轮实际读取的每个小型源文件都登记前后指纹，包括计划、复用的阶段一分类、原始汇总、stage23 manifest，以及已终止试验的 monitor、退出码、归档源码清单和要求的评价 JSON。前后读取使用相同的单文件字节上限；缺失路径也登记，因此“缺失后新建”、删除、内容/mtime/大小或解析状态变化都会使工具拒绝输出混合快照。历史阶段一分类中列出的每份原始试验 JSON 不会在本轮全部重新打开；它们仍依赖先前已保存的独立分类证据。

## 特殊结果的处理

| 分类 | 含义 |
|---|---|
| `SCORED_PASS` | 原台账及全部要求的可读评分一致通过 |
| `SCORED_FAIL` | 原台账 FAIL，并有正常生成、可解码的明确 FAIL 报告 |
| `CONFIRMED_INFRASTRUCTURE_FAILURE` | 阶段一已有独立审计确认的 seed08，保留原正式 FAIL |
| `REPORTED_INFRASTRUCTURE_FAILURE` | 新记录 manifest 明确设置了基础设施停止标记；工具不冒充独立根因诊断 |
| `SCORED_NEGATIVE_OR_INCOMPLETE` | 原评价使用 `FAIL_OR_INCOMPLETE` 或其他混合/不完整标签，保留其歧义 |
| `INCOMPLETE_OR_UNKNOWN` | 报告缺失、解码证据不足、原评分与保存记录矛盾或被中断，需另行说明 |
| `NOT_TERMINAL` | 仅在明确请求部分快照时使用，不能计为完成或失败 |

阶段二评价器的返回码 2 配合有效 FAIL 报告属于正常负面评分，不能与异常退出混为一谈。阶段三云台评价器使用 `FAIL_OR_INCOMPLETE` 时，工具不会强行将它转换成确定的算法失败。阶段三同时需要 flight 和 gimbal 两份报告，缺少其中一项不能判作评分完整。

快照错误、持续跟踪失败等标签可以并存，只记录已保存的检查，不推断因果；所有原始检查的 false、null、缺项和评价限制保留在 JSON 中。后续物理身份、检测、状态精度等补充研究须另行引用，不能靠此失败分类工具推导出来。

## 单条或部分快照

已经使用真实保存报告完成的单条核对：

```powershell
python scripts/summarize_full_plan_failure_taxonomy.py --root results/frozen_fullplan_v3 --trial fullplan_v3_stage23_s2_car_crossing_locked_seed000 --output results/stage2_car_crossing_seed000_saved_report_audit
```

该目录已存在，工具会拒绝覆盖；需要新快照时另取目录名。单条模式始终标记 `SELECTED_TRIALS_SNAPSHOT`，不会声称已经完成 166 次。

如确需一次明确的部分快照，可以传入 `--allow-partial` 并使用新输出目录；仍未终止的槽位会列为 `NOT_TERMINAL`，结果标记 `PARTIAL166_SNAPSHOT`。这不是持续监控机制。

静态复核后已补全每份实际读取小源的前后指纹登记，并将该汽车 seed000 的新单条产物保存到 `results/stage2_car_crossing_seed000_saved_report_audit_v2`；旧单条目录保留，旧目录只对计划和 manifest 做全局前后比较。当前未运行全 166 次分类，没有执行测试或任何仿真/评价子进程。缺失路径在实际文件读取函数中登记，但没有执行并发缺失转新建的故障注入。默认最终门槛、阶段三混合结果及完整 166 次分支将在实际最终记录生成时被使用；本说明不声称它们已经在完整 166 次结果上验证。

