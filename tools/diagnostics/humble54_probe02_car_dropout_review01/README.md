本目录保存对汽车 dropout probe02 的独立像素审阅。Codex AI 子代理实际使用
`view_image` 查看 contact sheet，并逐张查看全部 9 张 640×480 原 PNG，
记录时间为 2026-11-03 09:27:01 UTC。未读取 bag/telemetry，未运行 WSL、ROS 或推理。

30.7、30.8、30.9 秒可见一辆灰色汽车背面及地面、天空；31.0、31.1、31.2 秒
画面近黑，仅有淡色调区域，不能辨认汽车；31.3、31.4、31.5 秒再次可见汽车。
这些是逐张实际阅图所得的像素事实，不能证明 tracker 恢复、同一物理个体或身份保持。

[阅图记录](visual_review_native01.json)保留每张原图 SHA、采集整数时间、作者和记录时间；
[归档清单](archive_manifest01.json)绑定原提取 manifest、9 张原 PNG 及 contact sheet 的逐字节副本，
位于 `evidence/input/`。所有文件按本目录 `.gitattributes` 保留原字节，原提取目录不改。

记录采用 `sensor_input_interruption_v1` 实际 `_review` 的字段及标签词表作为像素描述格式。
这不等于执行或通过整个工程合同。原槽 detector interruption 已为 true，短窗已有 2 条
diagnostic，并非该模块要补证的“零下游输入 detector=null”情形；另一个
`identity_preserved_on_observed_recovery=null` 也不能由画面重现补成 true。
该模块 `_original` 还要求身份等行为项为 bool，早于其 NOT_APPLICABLE 分支。
本次没有强行运行/改变该合同，不宣称 UPSTREAM_INPUT_INTERRUPTION_CORROBORATED。

原 FAIL、短遮挡后丢失 false 检查、身份 null、`first_measured_after_open_s=null` 全部保留。
[33 项输入机会描述](opportunity_description01.json)只从原 manifest 逐项列出：raw RGB/depth
各 9 项，research RGB/depth、diagnostic 各 5 项。31.3–31.5 秒原图有汽车，并不能据此
推断 detector、滤波、控制或 tracker 已恢复；本抽取窗对应 research/diagnostic 记录也不存在。

`record_review.py` 只固化已经完成的实际 AI 阅图并校验/复制固定 SHA 文件，不自动识图。
作者和记录时间为固定原值；重新运行不是一次新的阅图，也不会覆盖本次归档。
