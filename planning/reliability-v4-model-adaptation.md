# 精确命名的汽车检测候选登记接口

最新状态（2026-10-30）：第二轮固定`train20_04`框架best17完成新24图检查，48/48成功、0未知，原m为24 TP/1 FP/0 FN、候选24/0/0；完整逐对审计及根代理/独立代理实际三页视觉复核均未触发事前新增FP/FN或明显局部框退化拒绝条件。盲标先于预测，详见[新24结果、SHA与三列对照](reliability-v4-fresh24-results-20261030.md)。根代理决定将04作为新Humble29开发闭环候选，独立显式启用已完成原帧回放验证的`navigation_correlated_two_face_bound`；236图view038已知合并大框风险仍保留。下一步将下述04三份来源文件按原字节复制并核SHA，在新的开发来源冻结/四包冷构建后完成同源两类clean、12核心、4安全及16扩展。这里不声称新29构建或飞行已运行；候选选择仅供新开发源，正式整体仍DRAFT、0/280，尚无工程验收通过。

以下保留新24完成前的登记历史；其中“尚未比较/未复制/未修改协议”仅描述当时状态。01被拒绝的历史及04精确原字节登记继续有效，不能事后换epoch或混用来源。

**最新状态：第一轮train20_01在新10视角检查中退化（原m960为10/0/0，候选为8 TP/1 FP/2 FN），已拒绝直接替换。第二轮train20_04已完成固定20轮训练；236图开发比较总体改善，但存在一张图新增跨两车大框误检，后续新24图比较及闭环尚未验收。两份精确登记均只保留可追溯能力，不代表模型采用或验收通过。** 第一轮详见[候选执行记录](reliability-v4-car-repair-candidate-20261030.md)，第二轮详见[定向适配记录](reliability-v4-car-adaptation02-20261030.md)。

此接口只准备后续登记能力。当前正式协议继续使用 `models/yolo11m.pt`；本次代码变更不复制权重、不更改现有协议JSON、不启动候选或仿真。行人资源、汽车960图像尺寸/4线程/9m距离、全部评价阈值及身份/丢失保护保持原要求。几何开关独立声明，选择微调检测器不会自动开启它。

原模型之外只允许两个精确模型名，按`resources.car.model`动态查找各自的完整顶层`model_adaptation`对象。不得填写任意路径、其他训练轮次、不同来源SHA或事后选择的checkpoint；01与04的权重、receipt、manifest不能交叉配对。原模型协议不能夹带此对象。

第一轮train20_01的原登记保留如下：

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

两轮20轮训练均按事前规则使用框架的原始检测validation fitness选出的`best.pt`，其fitness权重为P/R/mAP50/mAP50-95上的`[0,0,0,1]`。CSV argmax只作记录精度下的诊断，checkpoint身份由固定SHA确定。训练receipt完整保留原框架选择和来源证据；此接口不重新载入、改写checkpoint或把开发验证改称独立测试。

第二轮train20_04独立登记如下。原始起点仍为`models/yolo11m.pt`，不接续已拒绝的第一轮候选；实际框架选择为第17轮的`best.pt`，不能换成`last.pt`或其他epoch。此登记中的training receipt特指infer04的原`frozen_inputs01.json`字节，保留其真实schema、训练终态SHA、best SHA和236图来源，不冒充第一轮的`frozen_training_receipt.json`。

```json
{
  "target_class": "car",
  "model": "models/yolo11m_car_sim_train20_04.pt",
  "model_sha256": "bf7a56de4ae1658f8101fc6089247e8b984c2965b58d6b4963b4b5977e9ca00c",
  "training_receipt": {
    "path": "config/car_sim_train20_04_training_receipt.json",
    "sha256": "8b0d87baebd54f3ee46f0fd3d91fbd11354c723adbc1406d8bcc69a888e028a5"
  },
  "dataset_manifest": {
    "path": "config/car_sim_train20_04_dataset_manifest.json",
    "sha256": "c7abb224412bd550f32dadc0e99c3ed627effc4f3d41e3769a6bf5ede143c128"
  },
  "training_epochs": 20,
  "checkpoint_selection": "PREDECLARED_FRAMEWORK_BEST_PT_ORIGINAL_VALIDATION_FITNESS_MAP50_95",
  "posthoc_epoch_choice": false,
  "scope": "DEVELOPMENT_ADAPTATION_ONLY"
}
```

后续准备新冻结根时，需提供这些文件和声明：

| 路径 | 内容及准备方式 |
|---|---|
| `models/yolo11m_car_sim_train20_01.pt` | 已冻结`best.pt`的原字节副本，SHA必须等于上表；保留原`models/yolo11m.pt` |
| `config/car_sim_train20_01_training_receipt.json` | 已冻结`frozen_training_receipt.json`的原字节副本，不能重新排版或改写内部历史路径 |
| `config/car_sim_train20_01_dataset_manifest.json` | 已冻结`dataset_manifest.json`的原字节副本，保持原样本、标签和来源记录 |
| `models/yolo11m_car_sim_train20_04.pt` | 第二轮`humble28_car_train02/runs/train20_04/weights/best.pt`原字节副本；禁止代用第一轮、last或其他epoch |
| `config/car_sim_train20_04_training_receipt.json` | `humble28_car_train20_infer04/frozen_inputs01.json`的原字节副本，不能重新排版、改写schema或内部历史路径 |
| `config/car_sim_train20_04_dataset_manifest.json` | 第二轮`humble28_car_train02/dataset_manifest.json`原字节副本，不能代用第一轮manifest |
| 新冻结根中的核心preregistration JSON | 在独立开发验证满足要求后，显式切换`resources.car.model`并加入上述完整`model_adaptation`对象；不得改写旧冻结协议 |
| 后续独立开发和正式plan/gate JSON | 由现有runner生成全新名字，保留全部失败；扩展计划继续绑定同一核心协议和模型登记 |

无需新增独立模型注册JSON层。receipt和manifest都位于现有`config`扫描范围，`.pt`位于现有模型扫描范围。`make_plan`用实际文件SHA核对精确登记，即使该次probe只选择行人，也不能让已经声明候选的协议缺失模型来源。`validate_plan`同时检查`source_hashes`、完整`model_hashes`和完整`config_hashes`，缺失或替换条目均拒绝；`verify_sources`继续逐字节核对实际树和原协议。

开发门同时比较每类**实际选择的模型**和适配登记。即使原模型、01、04预先共存在同一树中、文件池SHA完全相同，运行原模型或01的开发记录也不能用来证明启用04。实际运行仍由已登记的trial spec生成精确`--model-path`，并沿用run_config、运行YAML、源码/模型快照、独立评价和安全门的完整证据链。扩展计划复用同一精确登记、实际字节绑定和CLI检查；检测模型与两面相关几何界仍须分别显式选择。

当前实现只加入04注册能力，未复制上表任何04文件，也未修改核心或扩展协议JSON。后续采用须在新24图按冻结规则验收、已知局部回归保留并完成独立审查后，显式准备新具名冻结、实际来源文件、冷构建和同源闭环开发证据；正式种子不能用于选择候选。
