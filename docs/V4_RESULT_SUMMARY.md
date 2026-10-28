# v4轻量结果快照与配对统计

[summarize_reliability_v4.py](../scripts/summarize_reliability_v4.py)读取已冻结核心计划、可选独立扩展计划及逐槽小JSON。它不启动ROS、PX4、Gazebo或YOLO，不解压/反序列化bag。当前真实正式矩阵尚未执行；合成夹具通过只证明工具逻辑，不产生正式结果。

```bash
python scripts/summarize_reliability_v4.py \
  --core-plan /frozen/root/results/core/plan.json \
  --extension-plan /frozen/root/results/extensions/plan.json \
  --output /path/to/new_summary
```

只汇总核心时省略 `--extension-plan`。输入计划必须留在原冻结output路径；工具调用运行器 `load`、`validate_plan`、`read_slots` 核验计划摘要、槽记录摘要和终态工件hash。它还核对每份已登记report的原路径、report SHA、终态artifact SHA、schema、原评价结果与来源合同。缺少绑定、错误评价或不支持schema不提供数值，已改写的冻结工件直接拒绝。运行中的零散报告不会提前进入统计。

`read_slots`会流式核验终态清单中的工件文件hash，包括文本/JSONL；它没有bag reader，也不加载压缩数据库。大型研究首次核验仍有磁盘读取成本，应避免与正式重任务争用。正在运行的研究是逐槽只读快照，不声称跨计划原子时刻；已使用文件在输出前再次核hash。

输出目录须全新，包含：

- `index.html`：可直接打开的进度、原终态和主要物理误差表；
- `summary.json`：全部原槽、指标、删失、来源hash、分组和配对结果；
- `trials.csv`：每计划槽一行，缺失值留空；
- `group_metrics.csv`：按cohort/class/group/condition的试验级均值、样本SD、中位数、n及n_missing；
- `paired_differences.csv`：同seed配对均值/SD/区间及有限配对分母；
- `paired_trial_differences.csv`：每seed原状态、左右槽ID和逐指标差值，包括缺失配对。

核心120和独立扩展160分别计数，不混入v3。工具也支持开发PROBE子矩阵，原模式写入结果；开发1次不叫正式十次。原PASS、FAIL、INTERRUPTED、INFRASTRUCTURE_ERROR、INCOMPLETE_EVIDENCE、EVALUATION_PENDING、RUNNING和PENDING逐条保留。`ALL_PLANNED_SLOTS_TERMINAL`仅指所给计划的执行记账齐备；`all_engineering_pass`另看原PASS分母，`all_required_report_documents_available`另看报告缺失，均不能等同整个项目验收。

## 指标定义

导航直接读取新 `navigation_reference_evaluation.json` 的 `whole_interval.metrics.base_link_*` 与 `kf_navigation`，不拿旧surface锚点或model-origin误差替代。报告包含物理距离/高度RMSE与p95、KF位置/速度、navigation/独立真值覆盖、反侧超调和末端稳定时间。右删失、缺失、不一致三类稳定状态单列；稳定时间只对实际SETTLED试验有值，不能填0或据条件均值宣称全部稳定。

检测处理FPS采用仿真时间，推理耗时采用墙钟，采集至完成延迟采用仿真时间，三者分别命名。现飞行报告没有可见标签Precision/Recall/mAP，这些值不会从候选可用率推算；检测精度仍由[独立检测来源/审核流程](DETECTION_EVALUATION_PROVENANCE.md)另交付。

云台包含检测框归一化中心误差、独立真值地平线误差、采集时刻TF覆盖和反馈误差。身份包含REQUEST至完整Clock的已知覆盖、保守保持下界、wrong/unknown，以及先任务均值再按飞行统计的amodal/unoccluded HOTA、IDF1、ID Switch。无GT和预测的空任务不制造0次ID Switch。amodal诊断不自动成为可见检测标签；显式重选不称完整ReID。

不存在、非有限、布尔冒充数值、负RMSE或超出[0,1]的覆盖值均保留null。每个group的n_missing包含该组全部计划槽，不能通过只保留成功飞行改变分母。不适用云台/身份评价与应有但缺失的评价另列。

## 配对规则

核心同class/seed比较 `stage3_active − stage3_midpoint` 和 `stage1_position − stage1_velocity`。独立扩展使用预先记录的 `comparison_reference_id` 比较 `extension − clean core reference`；正式扩展还要求本次输入核心计划与 `core_reference_binding` 的实际路径、文件SHA、计划摘要及reference IDs完全一致。核心/扩展飞行关键源码、模型、协议、渲染和运行环境绑定不同时拒绝配对；同类别不同seed不能配对，也不合并旧Jazzy试验。扩展登记与开发关口已披露的 `known_algorithm_failures` 在JSON中单列，不能混入正式分母或被后续成功覆盖。

每指标分别报告全部有限配对和双方原工程PASS子集。FAIL但可测的试验保留在全部有限配对中；缺失或待运行的一侧产生null差值，计划分母不减。每类/条件正式计划为10对；开发子矩阵的实际计划对数另存，不能把10这个设计数当实测n。负差只表示左侧该指标更小，对FPS/coverage等不能自动解释为更好。

默认95%配对百分位bootstrap，10,000次，RNG seed20261029，可由 `--bootstrap-resamples` 与 `--bootstrap-seed` 明确设置并记录。重采样单位是已经形成左右差值的trial/seed块，不能按帧或窗口增加独立样本数。区间仅条件于实际有限配对/成功子集；不足两对或所有差值相同则标明不可估计/退化，不制造精度。正式论文所用统计参数应在正式结果出现前固定，此工具不代替前瞻登记，也不产生闭环因果或显著性结论。

轻量检查：`python -B -m unittest discover -s tests -p test_reliability_v4_summary.py -v`。全120/160、旧状态、缺包、删失、配对、来源篡改等检查均使用明确合成JSON；未读取真实正式录制。
