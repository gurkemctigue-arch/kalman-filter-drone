# final55 冷构建前的离线叠加与冻结顺序

本说明记录 2026-11-03 已审候选的精确文件及未来执行顺序，补充 `reliability-v4-final55-source-staging.md`，不修改原卡、冻结54或历史收据。本次仅在 Windows 读取小源码、Git差异和原计划/完整源码映射元数据；未建立 staging，未运行 WSL、模型读取、冷构建、实际导航28次复评或真实 gate。

原卡中“最终55仍全部等于原308/185哈希”的命令只适用于**叠加前的54复制基线**。本版保留该基线检查，随后只叠加下列10份文件及预先声明的主协议 descriptor，建立本版自己的预期和实际 map。不要直接重放原卡第3、4步的旧哈希断言来检验新离线版本。

## 已核对的原始输入

| 原始小文件 | 文件 SHA256 | 内容摘要/范围 |
|---|---|---|
| `results/frozen_fullplan_v4_humble54/reliability_v4_humble54_core12_probe01_matrix/plan.json` | `ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b` | `plan_sha256=3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31`；PROBE，seed `[4]`，12槽 |
| `results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe01_matrix/plan.json` | `f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055` | `plan_sha256=ded5ab19b72f53c932cbea2044561a4e2fe937445cb07eb9525e9e0be5fc9761`；EXTENSION_PROBE，seed `[4]`，16槽 |
| `results/frozen_fullplan_v4_humble54/freeze_validation/source_integrity/source_before.json` | `cdb4111738f2f51c9911e3e7cebaf9f69aafd92d5cef39d8839a1e5dbb27c82f` | 1585项 rsync-filtered 原始完整源 map |

两个计划的 `source_hashes` 字典相等，均为308项。按未改变的分类规则，原 map 有30项离线源、277项 flight 源，另有独立排除的 runner；其中 scanner 可见源码为185项。不能把277项解释为飞行进程实际 import 集合。

以下仍全部保留54字节：六个模型、五个 runtime registration、所有在线算法/模型/配置、除具名叠加外的其他离线 evaluator/helper，以及原真实 `research_report.json`。本次没有读取六个模型载荷，仅核对了原计划中的元数据。

## 固定10份文件叠加

表中旧值来自54的原 `source_before.json`/计划，新增文件的旧值明确为 `null`。新值来自本次工作区小文件实际字节。执行时先核对全部 before 和 source pins，再只写全新 staging；不能复制整个当前 `scripts`、`tests` 或 `tools`。

| 路径 | 54旧 bytes / SHA256 | 55候选新 bytes / SHA256 |
|---|---|---|
| `scripts/evaluate_navigation_reference.py` | 38019 / `bbff6c746ed76d0139c194cdfc1409f38dc422d64ddbc73da2995a0838df4422` | 38185 / `b49984d495ec7b12e623e961f3d606958aaef682ddfbc636f9c21ed2d52abcb4` |
| `scripts/build_reliability_v4_probe_gate.py` | 24430 / `cf28d5455ceaa1eb52c498ba1048782c2fea35b65a0c8b2af4bddffae633d36f` | 41607 / `fa7d150a0e68b4678d0727139e206e20a629971d7bfeae0882d0f804381185ae` |
| `scripts/run_reliability_v4.py` | 168418 / `069c7c519d5b0305c087f8ad2597a2c709b367cc6c62624bbb686c9a0d158e11` | 182356 / `eab5c1b9ed8a5d3c304f6986aaf959a49a4349356aedb6335c36683895a217ba` |
| `tests/test_navigation_evaluation.py` | 30212 / `7d93c359bc0827d33f2f615dc5033ee98ee9d286c90a280213c7dec216f9bfb0` | 34500 / `634b8f5fe8f7e94de8747f68bba754196e865a2896f63c5f07bb36c5bca79510` |
| `tests/test_reliability_v4_probe_gate.py` | 19222 / `628b74d562ce6f8e9255a2c3e990e95983e1e7f63081b77ce5ce1bae73ab1ded` | 53086 / `38c88e55f5d8b75c3c4f8c7e90ba4920a29fbd02fda21979dfe44886bb64a5ea` |
| `tests/test_reliability_v4_runner.py` | 121066 / `07157bb4ea05abab0fb8ebd46b411f302ce4fa437d9e4858449d0a7920d796c3` | 121218 / `c0852dea246bcde137461e9fbf3af74b0c01246127433da6b90e8af682b20f44` |
| `tools/diagnostics/reliability54_build01/record_native_validation.py` | 7622 / `9cfd2d181b943df7551c912813e674635a66cef06ec409141d4a6cba33f3b0e8` | 10873 / `a3f177546432f698b8d7acabf0c4e2229fe42db524e7ff9da7cf0791bd5b33a6` |
| `tests/test_frozen_fastcdr_selection.py` | 3466 / `bee6e644f1e47554e31932afb2302c80c9a05d0d114011e19d4c9d0843f745c2` | 3817 / `ef36ab0e9055fb2eb74880756ab83a89b6bd4f023467aa0819b02a3217deb0c6` |
| `tools/offline_evaluation/sensor_input_interruption_v1/evidence.py` | `null`，原树不存在 | 33761 / `f3ce374272d750fc058cb98c5c8782f96a977c59aeade59afe0c5a2a80b4a5ba` |
| `tools/offline_evaluation/sensor_input_interruption_v1/test_evidence.py` | `null`，原树不存在 | 28796 / `c577a1010381d2cd3afb698a18fb25c1849aea5b454c503aa7d16310688b8154` |

共10份：3份源文件、3份导航/caller测试、原2份 native helper/test、2份新增模块/测试依赖。原先“3+2+2+2=9”的清单未包含导航修复自身的回归测试，本版明确将其作为第10份必需文件。`tests/test_reliability_v4_extensions.py` 和 `tests/test_follow_dynamics.py` 当前字节与54原完整 map 相等，无需叠加。

新增模块/测试在 staging 内的这两份副本只用于完整源码闭合及合成测试依赖。新 caller 测试会从 `fixtures.ROOT/tools/offline_evaluation/sensor_input_interruption_v1/` 读取它们，漏复制会导致 cold 套件缺文件。**实际生产 descriptor 继续绑定55和54根之外的独立模块，不能指向55内测试依赖副本。** 无需为了此依赖再修改测试。

不要叠加当前 dashboard、report、publication、lineage、其他 planning 文档或整个工具目录。尤其不能顺手更新 `evaluate_stage1_flight.py`、physical-identity、source-clock、native-startup、gimbal及其共享 helper：导航清单只覆盖 navigation，其他原报告的 provenance 必须仍与目标版本精确一致。

## 外置模块、合同与 descriptor

实际消费使用一套独立、具名且只写一次的外置工具/合同。推荐未来新目录为 `/mnt/d/WSL/UAVHumble22-validation/final55_input_evidence_tools01/`；该目录本次尚未创建。模块可从表中固定源复制为 `evidence.py`，合同可从已有 `tools/diagnostics/humble54_input_evidence02/contracts/contract_canonical02.json` 逐字节复制；复制后核实际字节和 canonical 路径，并保存独立来源收据。模块的定向测试和README可在外置工具目录归档，不因此添加到55。

现有 `contract_canonical02.json` 的实际小文件 pins：1314 bytes，文件 SHA `f4f5d040b9701dcd6a2fcafbcb672699ba2c16940c1f712756d5d83193e93ea0`，canonical JSON SHA `35f61541d5eab4fddd856a9c4b9ed76f2d6e0c66a8d172cf94256129e2315c17`。这是**后验开发来源固定合同**，不是正式实验的未来预登记或完整四槽通过收据。已有失败/INCOMPLETE尝试保留；若后续确需新合同字节，应另存新具名版本、重新审查并在 cold 前决定 descriptor，不能在 cold 后替换 pins。

合同固定原 extension 计划和以下四个槽，不能根据结果删改：

| slot_id | 类别 | 工况 |
|---|---|---|
| `person_extension_dropout_seed004` | person | dropout |
| `person_extension_combined_seed004` | person | combined |
| `car_extension_dropout_seed004` | car | dropout |
| `car_extension_combined_seed004` | car | combined |

在 staging 的 `planning/reliability-v4-preregistration.json` 中，**在 wrapper 采集 `source_before` 前**加入以下 descriptor。示意路径须在实际环境中先存在并逐一核验；这段是未来字段说明，本次没有写入实际协议：

```json
{
  "development_input_interruption_evidence": {
    "schema_version": 1,
    "revision": "sensor_input_interruption_v1",
    "scope": "DEVELOPMENT_EVIDENCE_ONLY_NOT_FORMAL_ADMISSION",
    "evidence_basis": "POST_HOC_DEVELOPMENT_SOURCE_BINDING_NOT_FORMAL_PREREGISTRATION",
    "module": {
      "path": "<外置evidence.py实际canonical绝对路径>",
      "sha256": "f3ce374272d750fc058cb98c5c8782f96a977c59aeade59afe0c5a2a80b4a5ba"
    },
    "contract": {
      "path": "<外置contract_canonical02.json实际canonical绝对路径>",
      "sha256": "f4f5d040b9701dcd6a2fcafbcb672699ba2c16940c1f712756d5d83193e93ea0",
      "canonical_sha256": "35f61541d5eab4fddd856a9c4b9ed76f2d6e0c66a8d172cf94256129e2315c17"
    },
    "source_plan": {
      "path": "/mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe01_matrix/plan.json",
      "sha256": "f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055"
    },
    "dev_slots": [
      {"slot_id":"person_extension_dropout_seed004","target_class":"person","condition":"dropout"},
      {"slot_id":"person_extension_combined_seed004","target_class":"person","condition":"combined"},
      {"slot_id":"car_extension_dropout_seed004","target_class":"car","condition":"dropout"},
      {"slot_id":"car_extension_combined_seed004","target_class":"car","condition":"combined"}
    ]
  }
}
```

`module/contract/source_plan.path` 必须等于 WSL 实际 `str(Path(path).resolve(strict=True))`。合法的 `/root/.../results` 链接写法即使 SHA 相同，也不能替代解析后的 `/mnt/d/...` canonical 字符串。不能把 Windows 路径填进 WSL descriptor，不能把 JSON 的Unicode转义文字当作文件名，也不重写原计划内部的历史路径。

外置模块、合同及最终四槽 evidence manifest 不能位于新旧 frozen root、原计划输出目录或任一原 trial 目录中。最终四槽清单由真实提取/阅图文件组成，调用端绑定其文件 SHA 并重算全部4槽；不是填入四个PASS标签。缺任何一槽、其他必需未知、安全失败、来源不符均拒绝。完整四槽清单可在 cold 后于外部新建，descriptor 不包含清单的未来虚构 SHA；其实际输出 SHA及模块重算结果由 gate 保存并重验。

## 两层 source-map 比较

先按原卡建立全新 staging，跳过54顶层 `results` 符号链接；只排除两个具名 nested build 目录，合计15+2=17项。保留54原17项及stale事实，不清理54，不扩大公共 freeze 的过滤规则。建立普通 staging results 目录，并复制原真实 research report。

此时先完成原54复制基线检查：完整308项名集和哈希相等、185项实际 scanner 名集和哈希相等、六模型/五runtime字节相等。完整源树基线另外以原1585项 map 扣除具名17项为预期，按实际公共 rsync 过滤比较每个路径/类型/字节；不是只比较计数。保存一份新的外部基线收据，保留原54 map。

完成基线后才写固定10文件和主协议 descriptor，并生成新的外部 overlay 收据，逐文件保留 before/after bytes与SHA、来源版本、审查引用及执行UTC。两份新增文件的 before 必须是实际不存在；任何原定文件提前改变或输出已存在都停止，保留尝试。

新308项 map 从原计划字典复制，只替换以下三个键的 SHA，其他键和值全部保留：

```text
scripts/evaluate_navigation_reference.py
scripts/build_reliability_v4_probe_gate.py
scripts/run_reliability_v4.py
```

由表中候选字节推导的**预期** map 摘要如下。canonical JSON定义为 `json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()` 再取SHA256；这些值不是实际 staging/cold 收据。

| 字典 | 项数 | 原基线 canonical SHA256 | 预期叠加后 canonical SHA256 |
|---|---:|---|---|
| `source_hashes` | 308 | `8a11b73428d6d4adacc042a41072a2e4da1dd7ed17756760073958f44ed21cb9` | `e1d22d7a858aa37eb382b6b365f3fdaeff09803be3669831dc92efbb2a8150b3` |
| scanner map | 185 | `f6a93f48822ba3d11d8e24c7a28939d512b5b1fbc472bcfb6cc5fdba4e957841` | `bdd24da4b8378ffb5502940913096fbd7b3499335de037536bee50e20f1fbde4` |

未来实际核验必须同时成立：

```python
assert set(actual_source) == set(original_source)
assert actual_source == expected_overlay_source
assert new_runner.flight_source_hashes(actual_source) == old_runner.flight_source_hashes(original_source)
assert len(actual_scanner) == 185
assert actual_scanner == expected_overlay_scanner
```

执行 old/new 函数前分别核其原/新 runner SHA；不要导入未核来源的当前默认ROOT。分类白名单及扫描规则不改变。不能只检查 `len()==308/185`、不能把所有离线差异都自动允许，也不能把上述预期摘要冒充实际测量。

完整 rsync-filtered map 与308项 map不同：10份叠加中8份替换、2份新增，主协议 descriptor替换既有路径；从原1585减17推导的复制基线为1568项，如无其他差异则 pre-cold 完整源预期为1570项。实际收据必须核对完整路径集合和值；descriptor真实字节及完整map SHA只能在实际写入并扫描后产生。测试/工具依赖和 descriptor不进入308/185，却必须进入本次完整 cold map。

## 冻结和真实复评顺序

1. 等原28槽及其owner/子进程闭合；原始失败与未完整尝试保留，单一重原生任务约束继续有效。当前剩余原槽由root既有 collector负责，本说明不启动另一个任务。
2. 审定固定10份字节及外置模块/合同；记录实际审定版本。当前Git差异不等于可直接复制整个工作区，也不能把动态HEAD当作自动批准。先核54完整复制基线，再只做具名叠加及 descriptor，最后核新的实际 map。
3. 从 staging 自身调用原公开 `tools/diagnostics/reliability54_build01/prepare_and_validate.sh`，reference仍为54。它必须在所有叠加后采集 `source_before`，完成真实 cold colcon、import/ament隔离、完整测试和 native validation。原公开wrapper、freeze脚本及过滤常量不改；55保留自身 `source_before/source_after/frozen_actual`、原始DRAFT档案及失败收据。冷构建后的实际scanner也须核更新后的185项哈希，无旧17副本；单模型+DDS保存快照仍应为185+2=187项。
4. 在实际 cold 完成的新55根中生成未飞的 core12和extension16 target快照；生产 publication要求两个target的seed均为 `[4]`、所有槽始终PENDING、source map相同且等于55实际 map。不能用合成测试的seed7/8、workspace或staging路径代替真实target。三个顶层协议仍DRAFT，原 `navigation_acceptance` 数值、REGISTERED状态和来源绑定不变。
5. 使用55自身实际 builder，按原两个计划登记全部28次未来导航命令，随后才执行。登记前选择全28都尚不存在的新plain JSON basename；若单次诊断占用了默认名字，另选统一新名字，不能覆盖或从登记中剔除该槽。

```bash
# 下列变量必须由当时实际存在并核验的路径提供；本段未执行。
tracking_core_dev="$(realpath -e -- "$tracking_core_dev")"
tracking_ext_dev="$(realpath -e -- "$tracking_ext_dev")"
tracking_core_target="$(realpath -e -- "$tracking_core_target")"
"$tracking_python" -B "$tracking_final/scripts/build_reliability_v4_probe_gate.py" \
  --target-plan "$tracking_core_target" \
  --probe-plan "$tracking_core_dev" \
  --probe-plan "$tracking_ext_dev" \
  --register-navigation-reevaluations \
  --navigation-report-basename "$tracking_new_navigation_basename" \
  --output "$tracking_external_nav_registration"
```

登记器只保存28条固定命令和来源/原terminal/原report SHA，不执行评价，不创建gate。其 `evaluation_root`、实施源SHA、命令wrapper/evaluator必须全部绑定实际55；不能复用workspace、staging或先前单次诊断来填写正式完成清单。

6. 串行执行登记里的每条原样命令，保存真实started/finished UTC、整数exit0、日志SHA、新report SHA；一次只处理一个重任务，不伪造完成记录，不覆盖新输出重试。原导航报告和终态保持原样。完成清单必须包含全部28唯一槽；任一gate都会独立核验全部28的执行、来源、网格结构，再消费自身12/16子集。结构完整的真实性能FAIL仍是FAIL，不被改成缺证或PASS。
7. 建立完整固定4槽真实sensor evidence manifest，在外部保存；通过声明固定模块独立重算4槽。两份已有行人证据不等于四槽完成。原短detector null仅在零输入机会和完整证据时记为UNOBSERVED附录；有诊断的False是已知失败且NOT_APPLICABLE，无诊断的False为矛盾缺证。short其他必需检查、long4项shutter+5项安全、source/native/recording和导航门均不放宽。
8. core gate提供原core计划和同一完整28导航清单；extension gate提供原extension计划、同一完整28导航清单及 `--sensor-input-evidence-manifest`，并给出晚于全部原16槽结束、且不在未来的真实verification cutoff。sensor参数只用于extension。新导航清单与旧六槽gimbal清单互斥，不能混装；本次不改gimbal评价器。
9. 严格验证gate后，再按normal card进行真实安全assembly、协议publication、正式120/160定义、replay assembly/publication、固定外置guard准入和新的完整final sidecar。target始终不飞。开发证据完整不等于原工程PASS、总体项目验收或形式实验准入。

## cold 后的不可变边界

descriptor及全部10份文件必须已包含在本次55的DRAFT cold基线里。cold后不能补代码、测试、工具依赖、README、本说明或变更descriptor路径/SHA；确需修改时应创建新的冻结尝试。

cold后只允许原normal publication的三个既有planning规范路径发生规定变化：

- `planning/reliability-v4-preregistration.json`：只改顶层`status`、`registration_utc`。
- `planning/reliability-v4-extension-preregistration.json`：只改`status`、`registration_utc`及真实`development_readiness`。
- `planning/reliability-v4-estimator-replay-preregistration.json`：只接受真实registrar产生并验证的replay candidate字节。

因此`development_input_interruption_evidence`不是可在publication时追加的字段。最终sidecar比较55自己的完整DRAFT cold map与最终实际树，保留原map和原cold收据，不要求最终55等于旧54，也不改写旧54地图。新增/缺失源路径或超出三规范路径的变化仍拒绝。

## 已有验证的实际边界

- Windows串行完整builder合成模块：19项通过，180.440秒；包含导航全28固定矩阵和sensor四槽接线合成情形。
- 最后外置源码bytes载入强化及真实外部模块合成fixture接线后：5项sensor测试通过，27.262秒；其中实际加载固定模块，但输入为临时tiny PNG/JSON，非真实实验。
- runner拒绝旧裸导航override的单项：通过，11.301秒。此前误并发测试轮触发既有machine-wide锁，13项错误；该轮不作为通过证据，随后串行19项通过。
- 已接受导航endpoint修复的35项及follow-dynamics的14项Windows测试通过；导航回归测试列入本次第10份叠加，55 cold套件仍须实际运行。
- 独立静态复核确认导航登记路径冲突、完整28数值结构、sensor4边界、canonical路径和直接执行绑定源码bytes的约束；未把静态复核当作实际gate收据。

这些事实不证明新55已staging、cold/native已通过、真实28复评/完整sensor4已完成、正式准入已发布或任何算法优越性。后续以各实际新收据为准。
