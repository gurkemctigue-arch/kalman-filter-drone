# 上游输入中断的独立证据校验

`evidence.py` 仅使用 Python 标准库，只读已有的小 JSON、原始元数据、已冻结的 reader/fault 源文件及导出的 PNG。它不启动 ROS/WSL，不读取 rosbag 载荷，不运行检测器，不根据亮度判断遮挡，不写报告或修改原记录，也不提供正式执行或准入入口。

公开 API：

```python
evaluate_slot(plan_path, slot_id, extraction_manifest_path, visual_review_path, contract) -> dict
evaluate_development_manifest(manifest_path, contract) -> dict
```

## 可选的短时丢失后身份不可评价分类

默认继续拒绝额外的身份 `null`。仅当另一个明确绑定 SHA 的新合同含以下精确字符串时，
才启用条件分类；`true`、`null`、拼写近似值均不接受：

```json
{"conditional_identity_rule": "CONDITIONAL_UNOBSERVED_AFTER_DEMONSTRATED_SHORT_LOSS"}
```

这完整复用 collector07 的严格短窗谓词：short 必须 complete 且结果 FAIL，
`no_loss_during_short_occlusion` 必须是 False，身份键必须存在且为 null；
`first_measured_after_open_s`、`recovery_after_open_s` 必须均显式存在且为 null，
`post_open_measured_missing_receive_time_count` 必须是严格整数 0。原 terminal 的
status/engineering_result 和 surface acceptance 必须仍全部为 FAIL。
start/end/first_lost/trial_end/recovery_window/duration/max_prediction 都必须是有限、
非 bool 的原始数值；duration 必须与 end-start 一致且不超过 max_prediction，
first_lost 必须位于 start 到 min(trial_end, end+recovery_window) 内。

`conditional_nonobservations` 单独保留该分类、原 null、原 FAIL、原 engineering_result、
first_lost、恢复观察窗口端点，以及 `identity_result=UNOBSERVED` 和
`identity_switch_observed_or_excluded=NEITHER`。它表示没有可比较的恢复事件，不能声称
身份保持成功、没有发生身份切换，或从身份评价分母删除该机会。
已知 False 继续进入 `known_algorithm_failures`；其他必要 null、缺时钟、shutter 或
长时丢失安全 False 仍拒绝。上游输入旁证不升级成物理身份或导航成功。

runner 在重新执行已绑定 module 后，对原始 SHA 绑定的 terminal/report 再计算完整谓词，
要求条件产物与原值精确一致。该身份 null 仍作为 UNOBSERVED 保留在失败披露和单独附表中；
所有物理导航门、原终态和原始文件不变。旧合同、frozen54 和已暂存版本不会自动启用新规则。

所有路径都必须在调用环境中真实可解析。模块不转换 Windows/Linux 路径，不解码路径里的字面 `\\u...`，不修改旧审图文件。原提取清单使用 Linux 绝对来源路径时，应在具备这些真实路径的环境中校验；Windows 单元测试只使用临时合成文件。

## 三种结果的含义

- `UPSTREAM_INPUT_INTERRUPTION_CORROBORATED`：这个短窗口的原始图像与确定性输入丢弃证据完整。此时原检测中断检查仍为 `null`，因为检测器没有收到该窗口的输入机会。这个结论不等于原工程 PASS。
- `NOT_APPLICABLE`：原短窗已有诊断帧、检测中断检查已有可评价的布尔结果，其余必需检查也已可评价；无需替代这个 `null`。这个状态仅指短窗替代不适用，检测中断本身或其他已知算法 False 仍单独保留为 `known_algorithm_failures`，不会因此被误标为输入证据缺失。无诊断样本却给出 False 的矛盾、其他必需未知、原安全失败和未列入合同的槽仍为 `INCOMPLETE`。
- `INCOMPLETE`：有来源、采集机会、阅图、固定矩阵、其他必需未知项或原安全门问题。返回具体原因并尽可能保留已读取的原结果。

`original` 原样保留原终态、acceptance 和短/长窗口的 checks/null。`known_algorithm_failures` 单独保留已知的算法 False，例如短时预测失败、短时丢失或恢复身份检查失败，以及长窗检测/预测/重选后持续跟踪失败。它们可以与充分的输入中断证据同时存在，附件不会把 False 改成 True，也不会把已知失败变成缺证。长窗丢失、悬停、持续低速、禁止自动恢复和重选前禁止跟踪控制仍必须为 True。

导航及其他既有工程门由调用者继续执行；模块无法替调用者将导航失败变成通过。原始检测器在这些丢弃帧上没有被测试，遮挡与注入丢帧的各自贡献也不能从本附件中分离。没有 `ready` 字段或隐式人工审批步骤。

## 显式合同

没有科学参数默认值，也不生成或伪造预注册。调用者必须提供一个 JSON 可序列化的合同，至少包含以下字段。占位文本是 schema 示意，不能作为真实证据使用：

```json
{
  "schema_version": 1,
  "revision": "sensor_input_interruption_v1",
  "scope": "DEVELOPMENT_EVIDENCE_ONLY_NOT_FORMAL_ADMISSION",
  "fault_algorithm": "SHA256_SEED_COLON_WINDOW_FIRST8_UINT64_DIV_2POW64_LT_FLOAT_FRACTION_V1",
  "drop_window_ns": 200000000,
  "drop_fraction": "0.10",
  "padding_s": "0.3",
  "extractor_sha256_by_condition": {
    "dropout": "<实际冻结的提取器 SHA256>",
    "combined": "<实际支持 combined 的冻结提取器 SHA256>"
  },
  "source_plan": {
    "path": "<实际原 EXTENSION_PROBE plan.json 绝对路径>",
    "sha256": "<该文件实际 SHA256>"
  },
  "dev_slots": [
    {"slot_id": "<原计划 person dropout 槽>", "target_class": "person", "condition": "dropout"},
    {"slot_id": "<原计划 person combined 槽>", "target_class": "person", "condition": "combined"},
    {"slot_id": "<原计划 car dropout 槽>", "target_class": "car", "condition": "dropout"},
    {"slot_id": "<原计划 car combined 槽>", "target_class": "car", "condition": "combined"}
  ]
}
```

四个槽必须来自同一个实际、摘要一致的原开发计划，并精确覆盖两类别 × 两工况，不能按结果挑选。合同可以为两工况显式绑定不同的提取器版本；模块不会猜测某个 SHA 是否支持 combined。原传感器故障源文件与计划 SHA 绑定，逐帧复算原 `seed:window` SHA256 前 8 字节、原 float 比较和 200 ms 窗口算法。

单槽 API 也要求完整的固定四槽合同，但不会要求另外三个槽已经产出证据。因此真正四槽未齐时仍可返回该单槽证据。合同及模块源码的实际 SHA 会包含在返回报告中。

## 原件与提取证据

校验原计划/终态内容摘要、原 flight 命令及成功退出/无残留、原 surface/source-clock/native 报告和执行条目、录包闭合与完整性、metadata、sensor faults 及原 reader/fault 源码 SHA。source-clock/native、闭包与完整性必须 PASS；原 surface 必须无读错/无缺话题且确有 armed/offboard。只有短窗 `diagnostic_frames_inside=0`、对应检测中断检查为 `null` 的情形可以补证。其他必需检查不能未知，原 shutter ACK 与长窗安全必须完整。

提取器必须已经完整扫描原六话题，无错误、无缺话题、Clock 回归为 0，使用原短窗前后固定 0.3 秒的全部机会；逐项校验整数图像 header、诊断的原整数 `acquisition_ns`、原诊断 JSON、记录顺序、各话题计数、RGB/depth 精确配对。原始 PNG 文件及接触表必须真实存在且实际 SHA 匹配；不接受挑帧或覆盖来源。诊断缺少整数 `acquisition_ns` 时本窄模块保持缺证，不自行补造精度。

全部窗口内 research RGB 和 research depth 的采集戳多重集合必须各自精确等于原 raw 输入按故障算法计算的 KEEP 集合。诊断采集戳必须是这两路实际共同交付机会的多重集合子集，不能出现未交付的帧；短窗前后各至少有一条匹配诊断。异步 latest-frame worker 和最大推理频率可以合法跳过周边已交付输入，模块不假设“一输入帧一诊断”，这些机会会原样列在 `delivered_without_diagnostic_acquisition_ns` 中，不据此降低传感器输入佐证。短请求窗的 raw 输入必须均属于 DROP，且该短窗 research/诊断均为 0。research 流本身的缺失、额外帧或不匹配仍为缺证。这个局部逐帧核对不替代原始全程录包完整性门。

## 独立阅图文件

这是已有实际人或 AI 阅图的记录，模块只核来源与明确观察，不声称自行进行了视觉判断。支持 `DIRECT_IMAGE_REVIEW_AI` 或 `DIRECT_IMAGE_REVIEW_HUMAN`，不要求用户本人审图。最小结构：

```json
{
  "kind": "INDEPENDENT_IMAGE_AND_INPUT_OPPORTUNITY_REVIEW_NOT_ORIGINAL_ACCEPTANCE",
  "review_type": "DIRECT_IMAGE_REVIEW_AI",
  "created_utc": "<实际阅图完成 UTC ISO 时间>",
  "reviewers": ["<实际阅图者与阅图方式>"],
  "manifest": {"path": "<实际 extraction manifest.json 绝对路径>", "sha256": "<实际 SHA256>"},
  "images": [
    {"file": "<原 PNG 文件名>", "sha256": "<实际 SHA256>", "acquisition_ns": 0,
     "observation": "TARGET_AND_SCENE_VISIBLE"}
  ]
}
```

`images` 必须保留全部原图机会及原顺序，与提取清单逐项匹配。可见观察值支持 `TARGET_AND_SCENE_VISIBLE`、原行人/汽车的 `ONE_PERSON_AND_SCENE_VISIBLE_IN_CONTACT_SHEET` / `ONE_CAR_AND_SCENE_VISIBLE_IN_CONTACT_SHEET`；阻断观察使用已有记录值 `SCENE_OBSCURED_NEAR_BLACK_TARGET_NOT_VISIBLE`。必须至少一张图在成功 close ACK 之后、open request 之前明确观察到场景被阻断，并有请求窗前后的可见场景。仅记录“像素低于阈值”不能代替直接阅图。提取完成与阅图时间均须为带显式 UTC 时区的 ISO 字符串（`Z` 或 `+00:00`），阅图时间不能早于提取完成；不接受无时区、非零时区或数字替代时间。

保留现有旧 review；若其类型或路径不符合此显式合同，应另存一个真实说明阅图主机、同一原 PNG SHA 和当前可解析来源路径的新 review，不能静默升级旧文件。

## 四槽清单

`evaluate_development_manifest` 接收以下结构，每个 path/SHA 都核实际文件：

```json
{
  "schema_version": 1,
  "contract_sha256": "<合同规范 JSON：sort_keys、紧凑 separators、allow_nan=False 后的 SHA256>",
  "source_plan": {"path": "<同合同>", "sha256": "<同合同>"},
  "slots": [
    {"slot_id": "<固定槽 ID>",
     "extraction_manifest": {"path": "<实际路径>", "sha256": "<实际 SHA256>"},
     "visual_review": {"path": "<实际路径>", "sha256": "<实际 SHA256>"}}
  ]
}
```

完整清单必须恰好包含四个固定槽，重复、额外或缺槽均为 `INCOMPLETE`。缺槽时保留已经完成的逐槽检查及 `missing_slot_ids`；不会生成完整就绪结论。即使四槽都得到佐证，也只是开发输入证据完整性，正式协议消费和 held-out 前冻结须由调用者另行完成。

运行本目录的小型合成测试：

```powershell
python -m unittest discover -s tools/offline_evaluation/sensor_input_interruption_v1 -p test_evidence.py -v
```

测试生成的源文件、原图、阅图文字均为临时 synthetic fixtures，只验证来源与边界逻辑，不构成真实实验或实际视觉观察证据。
