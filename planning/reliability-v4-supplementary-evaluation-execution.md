# v4 补充检测与时延评价执行卡

2026-11-01。本卡是后续实际执行顺序，不是实验结果。Humble42 在线冻结源、原 280 槽飞行矩阵、原失败记录和验收门均保持原值。

## 首次正式飞行以前必须完成

1. 继续原流程完成同源核心12、安全4、扩展16、实际28格容量统计、两条开发录制定标、独立最终根冷构建及真实协议登记。
2. 在最终根生成真正的 `FORMAL120` 和 `EXTENSION_FORMAL160` 两份计划；保留全部280槽尚未尝试的状态。
3. **此时、首次正式试验开始以前**，使用已独审的 `prospective_detection_dataset.py protocol` 创建实际补充检测协议。它核验原计划与全部280槽尚无试验目录/开始/终态产品，并绑定实际UTC、两计划SHA、冻结helper和生产工具。不能在正式数据出现后补建。
4. 将[补充选源清单](reliability-v4-supplementary-detection-selections.json)的实际SHA和新协议SHA保存到独立执行记录中；该清单不是协议本身，不授予飞行准入。随后完成原最终来源封存、容量准入和正式串行执行。

协议命令形态如下。大写参数须替换为真实物理路径和SHA；此卡没有执行命令：

```bash
python prospective_detection_dataset.py protocol \
  --core-plan ACTUAL_CORE_PLAN --core-sha256 ACTUAL_CORE_SHA \
  --extension-plan ACTUAL_EXTENSION_PLAN --extension-sha256 ACTUAL_EXTENSION_SHA \
  --output NEW_EXTERNAL_PROTOCOL_JSON
```

调用前必须按实际最终根加载Humble消息与原运行环境。工具源码见[检测快照](../tools/offline_evaluation/prospective_detection_v1/README.md)；源/工具发生变化时不能继续沿用旧协议。

## 正式录制齐备后的检测执行

补充选源固定复用既定12条演示来源：person/car、六个核心组、seed1000。它不新增飞行。每条按原计划的 `id` 查实际目录，无论原工程终态成功或失败都保留；缺失不换种子。原先两条单目标检测子集仍按[原执行卡](reliability-v4-detection-execution.md)处理并接入原报告器。

在独占资源窗口逐条执行新工具的 `extract`、`verify`、`labels`、`infer`。每条只能显式选择一个原slot；没有自动提取280条的动作。抽样为首个原FOLLOW后1秒起每2秒直到最终Clock，使用邻近0.1秒以内的原RGB，保留缺图、重复戳、遮挡、静默尾段和全部预定机会。多目标纳入全部同类物体；所有阶段三使用实际物理动态相机GT与反馈TF交叉核验，缺证不回退固定挂载。

独立代理实际查看原图与不含预测的全物体标签叠图，逐机会记录批准、拒绝或未知及理由；用户无需操作仿真或手工标注。然后执行 `review`、`evaluate`、`verify-report`，复用原schema2低置信度缓存、已保存飞行配置和原指标实现。全部执行使用新外部目录，不能写回原源码、计划、录制或其符号链接目标。

新报告保留完整280槽台账，明确其中预选12条的抽取/审核状态，以及其余268条未提供到该补充子集。它不能把未抽取项算成零误差或称为280条检测精度。指标仅描述实际独立批准的可见仿真子集；该报告经自身语义核验后作为单独附件，原Word报告器尚未接收其新结构。

## 时延执行与命名

[时延工具](../tools/offline_evaluation/timing_v1/README.md)也必须在录制停止写入且资源空闲后使用。显式指定原冻结源码、原试验、实际原计划输出保护根、原job日志和新的外部输出；先 `export`，独立核对context路径/SHA后再 `analyze`。导出与分析在同一路径环境进行。

分别报告原采集源时钟帧率、处理墙钟耗时、YOLO predict墙钟阶段、控制器报告的测量年龄及录包接收时钟速率。对缺失、重复、冲突和部分job保留未知分母。实际worker墙钟FPS及采集至PX4执行生效的因果端到端时延缺少完整端点，继续为 `NOT_OBSERVED`；不跨时钟相减、不用RTF换算。

## 交付接线

原正式工程统计、20录制×4估计器、两条原检测子集和固定12条视频沿原入口生成。新检测与时延附件另外索引实际协议、选源、原终态、生产源码、输入/输出SHA、独立图像审核和语义验证回执。代码/合成测试通过不代替实际评价。

最终计划书用报告器的显式 `--plan-content` 指向已更正的正文，绑定实际SHA，见[文档流程](../docs/V4_DOCUMENT_PIPELINE.md)。源树中的历史文字不会自动变成最终实验结论；最终Word/PDF须在真实资料生成后渲染并逐页检查。
