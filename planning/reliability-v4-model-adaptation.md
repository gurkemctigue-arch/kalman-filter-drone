# 唯一命名的汽车检测候选登记接口

此接口只准备后续登记能力。当前正式协议继续使用 `models/yolo11m.pt`；本次代码变更不复制权重、不更改现有协议JSON、不启动候选或仿真。行人资源、汽车960图像尺寸/4线程/9m距离、全部评价阈值及身份/丢失保护保持原要求。几何开关独立声明，选择微调检测器不会自动开启它。

只允许另一个精确模型名 `models/yolo11m_car_sim_train20_01.pt`，以及以下完整的顶层 `model_adaptation` 对象。不得填写任意路径、其他训练轮次、不同来源SHA或事后选择的checkpoint。原模型协议不能夹带此对象。

```json
{
  "target_class": "car",
  "model": "models/yolo11m_car_sim_train20_01.pt",
  "model_sha256": "7e7cadd59142cc6b891dc7de49298d445ca731cc72f4562896ed8e530bfc19bd",
  "training_receipt": {
    "path": "config/car_sim_train20_01_training_receipt.json",
    "sha256": "9d25d16bc5efb73dda87a5d3d4613b17b9dd6fe7598859b549a0c33baa56aaec"
  },
  "dataset_manifest": {
    "path": "config/car_sim_train20_01_dataset_manifest.json",
    "sha256": "21e66502037627e8dfd7bed4b6aba94351eab8075e29b24d28a9045e4234d23e"
  },
  "training_epochs": 20,
  "checkpoint_selection": "PREDECLARED_FRAMEWORK_BEST_PT_ORIGINAL_VALIDATION_FITNESS_MAP50_95",
  "posthoc_epoch_choice": false,
  "scope": "DEVELOPMENT_ADAPTATION_ONLY"
}
```

`scope`描述训练数据和模型选择所依据的开发范围。现有170帧已参与开发选型，其重复评价不构成独立泛化结论。该字段并不永久禁止正式登记；在后续独立视角、背景等验证和闭环开发门通过后，仍可事前冻结正式协议，再使用保留的正式试验种子。不能依据独立验证结果重新选择本训练的其他epoch并沿用本登记。

本次20轮训练按事前规则使用框架的原始检测validation fitness选出的`best.pt`，其fitness权重为P/R/mAP50/mAP50-95上的`[0,0,0,1]`。CSV argmax只作记录精度下的诊断，checkpoint身份由固定SHA确定。训练receipt完整保留原框架选择和来源证据；此接口不重新载入、改写checkpoint或把开发验证改称独立测试。

后续准备新冻结根时，需提供这些文件和声明：

| 路径 | 内容及准备方式 |
|---|---|
| `models/yolo11m_car_sim_train20_01.pt` | 已冻结`best.pt`的原字节副本，SHA必须等于上表；保留原`models/yolo11m.pt` |
| `config/car_sim_train20_01_training_receipt.json` | 已冻结`frozen_training_receipt.json`的原字节副本，不能重新排版或改写内部历史路径 |
| `config/car_sim_train20_01_dataset_manifest.json` | 已冻结`dataset_manifest.json`的原字节副本，保持原样本、标签和来源记录 |
| 新冻结根中的核心preregistration JSON | 在独立开发验证满足要求后，显式切换`resources.car.model`并加入上述完整`model_adaptation`对象；不得改写旧冻结协议 |
| 后续独立开发和正式plan/gate JSON | 由现有runner生成全新名字，保留全部失败；扩展计划继续绑定同一核心协议和模型登记 |

无需新增独立模型注册JSON层。receipt和manifest都位于现有`config`扫描范围，`.pt`位于现有模型扫描范围。`make_plan`用实际文件SHA核对精确登记，即使该次probe只选择行人，也不能让已经声明候选的协议缺失模型来源。`validate_plan`同时检查`source_hashes`、完整`model_hashes`和完整`config_hashes`，缺失或替换条目均拒绝；`verify_sources`继续逐字节核对实际树和原协议。

开发门同时比较每类**实际选择的模型**和适配登记。即使两个权重预先共存在同一树中、文件池SHA完全相同，运行原模型的开发记录也不能用来证明启用微调模型。实际运行仍由已登记的trial spec生成精确`--model-path`，并沿用run_config、运行YAML、源码/模型快照、独立评价和安全门的完整证据链。
