# 实际行人输入证据补充（两场，非完整四场）

2026-11-03 实际从 Humble54 原始 dropout 与 combined 录包分别导出固定短窗口前后全部机会，各九张原始 RGB 图像。root 使用 `view_image` 直接查看全部联系图，并另存 `DIRECT_IMAGE_REVIEW_AI` 记录，绑定实际 PNG SHA 与 native 可解析路径。提取器仍将原 manifest 标记为 `PENDING_VISUAL_REVIEW`；本附件不改写该文件或原实验判定。

| 原槽 | 直接图像观察 | 实际外部模块复评 | 保留的原结果 |
| --- | --- | --- | --- |
| person dropout | 31.4/31.5 秒近黑，前后可见行人 | `UPSTREAM_INPUT_INTERRUPTION_CORROBORATED`，errors 空 | 原 `INCOMPLETE_EVIDENCE`、detector interruption=null |
| person combined | 29.9/30.0 秒近黑，前后可见行人 | `NOT_APPLICABLE`：短窗已有检测诊断 | 原 `FAIL`；`surface:long:prediction_observed=FAIL` |

dropout 的九个原始 RGB/depth 机会逐一复算原 seed004、200 ms、10% SHA256 丢弃算法，得到五个 KEEP 和四个 DROP；两路 research 各五条、diagnostic 五条均精确匹配。短请求窗内的原始机会全部属于 DROP，因此检测器在这些帧上没有获得可评价的输入。这是输入中断的独立佐证，不能替代检测器在遮挡图像上的实际性能测试，也不能把原 null 写成 true。

实际首次模块调用保存为 `input_evidence_evaluation01.json`：合同中的 `/root/.../results` 是现有符号链接，模块要求显式规范路径，因而拒绝该路径绑定。第二次调用另存 `contract_canonical02.json` 和 `input_evidence_evaluation02.json`；只把 source_plan 路径明确解析为 `/mnt/d/...`，同一原文件 SHA、科学参数和固定四槽均未改变。首次缺证结果、原合同和执行脚本全部保留。

实际第二次模块调用为 `2026-11-03T03:38:29.236952Z` 至 `03:38:31.089676Z`，命令退出 0。模块 SHA 为 `f3ce374272d750fc058cb98c5c8782f96a977c59aeade59afe0c5a2a80b4a5ba`；新合同文件 SHA 为 `f4f5d040b9701dcd6a2fcafbcb672699ba2c16940c1f712756d5d83193e93ea0`。原始返回见 `contracts/person_evaluation_receipt02.json`。

本快照 52 个复制文件共 1,215,965 字节，root 已逐份核对原件与复制字节。清单 `manifest.json` 保存实际来源、大小与 SHA。它包含原计划、两份原终态及必要小型报告，未复制 rosbag 载荷；此处复核文件不能仅靠修改路径变成另一台机器上的原生验收结果。

合同始终固定 person/car × dropout/combined 四格。汽车两格尚未运行，因此这两份真实结果不构成完整四槽附件、工程 readiness、正式预注册或正式执行准入。导航与其他既有门继续单独校验，所有失败、未知和完整分母继续保留。

原六槽 collector 的后续实际核对还确认：combined 的导航距离 RMSE 为 2.296435 m，按原1.0m门复核数值为 FAIL。原 navigation 报告标签仍为 `RECORDED_WITH_CENSORED_FAILURES`，原 terminal 的顶层负面 evaluator 只有 `surface_flight`；此处不新增或改写原字段。本附件只校验输入证据，不将这项控制失败纳入其局部 `known_algorithm_failures`，也没有使它通过导航门。
