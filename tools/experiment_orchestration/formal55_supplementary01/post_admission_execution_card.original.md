# final55：封存准入之后的实际执行卡

状态：静态源文件、接口与metadata绑定核对完成；新55修订已独立静态审查，作者63项Windows合成测试通过。此卡没有创建实际检测协议、adapter identity、contract、launch request、guard state 或正式槽。

## 适用范围

前置流程以 `final55_normal_registration_execution_card01.md` 为准：正常新 final55 算法根、真实冷构建、开发门与 safety4、完整120/160定义、三项登记、真实 sealed admission、最终源码 sidecar。core12 / extension16 / R0 / storage 等现有准入条件全部保持。此卡只接续实际 admission，不能代替任何准入证据。

原 formal54 supplementary 的 canonical `b0c4f60b438455569f46f2160ac4bb0e46202fca311a57f9b25181fe7d4b680c` 只允许同根 guard，不支持本路线的固定外部审计 guard。因此不能直接把旧54 supplement用于新55；不得改旧54原件、改 admission.tool，或伪造历史41候选。新55修订限于显式支持下列已审固定外部guard，保留legacy同根分支、原小文件检查和所有后续门。

新55独立静态核对的canonical为 `b8f75eccb143871130671a00ad5cf75fe0768e43bc46bb0a99c2586f207b0580`。下文`tracking_supplement_reviewed_canonical`必须设置为此已审常量；不能从一个未经审查的describe自行授予接受。

固定外部审计 guard：

```text
/root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_guard.py
e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e
```

formal48 不需修改：`load_original_guard()` 使用 admission.tool 的已核字节编译，核 `module.__file__` 与实际绝对路径，再核 SHA。serial54 / durable54 接受实际新55 supplement 的 argv/path/canonical，未硬编码旧54 supplement。

## 真实接口与执行顺序

1. 从 admission.plans 读取实际 `FORMAL`120 / `EXTENSION_FORMAL`160 两个文件路径及字节 SHA；保持全部280尚未尝试。先前安全试验不属于280。
2. 用现有外部 detection producer 新建真实事前协议（如果已经生成，保留其原字节，不重造）。
3. 保存 actual Linux formal48 `describe` stdout、serial54 `describe` stdout、新55 supplement `describe` stdout。
4. 按下列 exact schema 新建 adapter identity，再新建 supplement contract；identity.created_utc <= contract.created_utc。
5. 执行新55 supplement `verify`，必须为只读验证通过。
6. 新建 durable launch request；source pins 包含新55的真实路径、describe、全部 manifest.files，以及其余明确输入。
7. 经原 durable54 `launch` 启动原 serial54；serial 最后追加 `run-one --manifest PATH`。不能自行追加 slot/retry/seed/数量选项。
8. 保存 launch ACK、registry文件字节 SHA、owner目录；使用 `watch` 观察，不能将观察器退出解释为实验退出。

首次 supplement `run-one` 先追加 `audit.jsonl`，随后 exec 原 formal48，原 guard `execute_one()` 再创建 initial_admission.json并启动正式槽。`verify` 不写 audit。原 `guard.check()` 只读，允许前面的 publication source-sidecar 调用；只有 `execute_one` / `run-one` 必须从 supplement入口进入。

依据：guard.check 1034–1070；state/initial写入仅 execute_one 1093–1101；supplement.run_one先 append_audit 再 exec；首次audit要求 initial_admission=None。

## 固定检测选源：不得重选

新 final55 根中的两个原样冻结文件：

| 相对路径 | 原文件字节 SHA256 |
|---|---|
| planning/reliability-v4-supplementary-detection-selections.json | 26aa2b18947e73f02749c128a0110825f67f7b8ba8f0cab238766bd31f0ecdd5 |
| planning/reliability-v4-delivery-selections.json | 5ff909b11eeaebcfc21a9268714dece7f1da13741713d374731618124d63d628 |

这些绑定稳定 slot IDs，未绑定历史 formal41 root/plan：person/car × stage1_velocity、stage1_position、stage2_crossing、stage3_midpoint、stage3_active、stage3_multi_active × seed1000，固定12来源。保留原时间戳，无须新selection builder。实际新协议绑定新55两计划与根，分母仍完整280，新增正式飞行0。失败/缺失的12来源不换成功seed。

```bash
bash "$tracking_final/scripts/run_research_session.sh" \
  /mnt/d/WSL/UAVHumble22-validation/prospective_detection_dataset.py protocol \
  --core-plan "$tracking_core_formal" --core-sha256 "$tracking_core_file_sha" \
  --extension-plan "$tracking_extension_formal" --extension-sha256 "$tracking_extension_file_sha" \
  --output "$tracking_protocol"
```

上述变量必须来自真实 admission/plans，不填历史示例路径。`--output` 为父目录存在、尚不存在的外部普通JSON文件，必须在算法根、results、trial/plan output及guard state以外。此CLI存在且会核实两计划完整120+160、相同源码/模型映射、extension核心引用和全部280无目录/start/terminal。不要把`FORMAL120`当作mode值。

已审外部 detection sources：

```text
/mnt/d/WSL/UAVHumble22-validation/prospective_detection_dataset.py
8ae476a9012a0a735bd185fe3df7a8c8ec06be82c3192668e2c5760a19a01ba2
/mnt/d/WSL/UAVHumble22-validation/evaluate_prospective_detection.py
7a4f91946f26b6ca28e66babdc45b6875bdebe61b8501b236b378ffa6882cc87
/mnt/d/WSL/UAVHumble22-validation/prospective_detection_independent_review01.json
0583f950a1557ece5988633d9c812f46b326f26c3bb15b4c5176303becd21a9e
```

## 事前 describe 与 identity

此部分命令是未来真实Linux执行，不是已执行结果。三个 stdout 必须分别完整保存为新的外部普通JSON，不拼接 stderr，不把 Windows describe重标为Linux。

```bash
bash /mnt/d/WSL/UAVHumble22-validation/formal48_dds_adapter01/formal48_guard_adapter01.sh describe > "$tracking_adapter_describe"
"$tracking_physical_python" -B /mnt/d/WSL/UAVHumble22-validation/formal54_serial_signal01/formal280_serial_guard54.py describe > "$tracking_serial_describe"
bash /mnt/d/WSL/UAVHumble22-validation/formal55_supplementary01/formal_supplementary_preflight.sh describe > "$tracking_supplement_describe"
```

`tracking_physical_python` 是真实物理解释器路径（例如解析后的 `/usr/bin/python3.10`），不能传符号链接。shell的固定路径保持 formal48 原外部位置。describe无正式准入或飞行；其来源仍须独立已审。

adapter identity精确字段：

```json
{
  "schema_version": 1,
  "kind": "FORMAL54_EXPLICIT_REVIEWED_ADAPTER_BINDING_NOT_ADMISSION",
  "created_utc": "ACTUAL_AWARE_UTC_BEFORE_CONTRACT",
  "shell": {"path": "ACTUAL_CANONICAL_FORMAL48_SHELL", "sha256": "ACTUAL_FILE_SHA"},
  "python": {"path": "ACTUAL_CANONICAL_FORMAL48_PYTHON", "sha256": "ACTUAL_FILE_SHA"},
  "describe": {"path": "ACTUAL_LINUX_DESCRIBE_STDOUT", "sha256": "ACTUAL_FILE_SHA"},
  "manifest_canonical_sha256": "dbc9358db20d02e62c2963b868605b4e77f4d16a188f52c5e28e11e20f9f2d5a",
  "reviewed_tools_sha256": "dbc9358db20d02e62c2963b868605b4e77f4d16a188f52c5e28e11e20f9f2d5a"
}
```

identity无builder CLI；按此字面schema用stdlib JSON原子排他新建即可，不能调用不存在的create-binding命令。读取真实describe的`manifest`并验证其canonical等于独立已审值；真实shell/Python/test三个同级原文件 SHA必须分别等于manifest.files。identity是绑定元数据，不是准入。

## supplement contract：精确schema与来源

下列是形状示例，不是可提交实际合同；所有`ACTUAL`值必须读取、计算真实文件。

```json
{
  "schema_version": 1,
  "kind": "FORMAL55_SUPPLEMENTARY_BINDING_ONLY_NOT_ADMISSION",
  "created_utc": "ACTUAL_AWARE_UTC_AFTER_ADMISSION_PROTOCOL_IDENTITY",
  "admission": {"path": "ACTUAL_SEALED_ADMISSION", "sha256": "ACTUAL_FILE_SHA"},
  "plans": {
    "core": {"path": "ACTUAL_CORE_PLAN", "sha256": "ACTUAL_FILE_SHA"},
    "extension": {"path": "ACTUAL_EXTENSION_PLAN", "sha256": "ACTUAL_FILE_SHA"}
  },
  "detection_protocol": {"path": "ACTUAL_PROSPECTIVE_PROTOCOL", "sha256": "ACTUAL_FILE_SHA"},
  "selection": {"path": "ACTUAL_FINAL_ROOT/planning/reliability-v4-supplementary-detection-selections.json", "sha256": "26aa2b18947e73f02749c128a0110825f67f7b8ba8f0cab238766bd31f0ecdd5"},
  "selection_basis": {"path": "ACTUAL_FINAL_ROOT/planning/reliability-v4-delivery-selections.json", "sha256": "5ff909b11eeaebcfc21a9268714dece7f1da13741713d374731618124d63d628"},
  "detection_review": {"path": "/mnt/d/WSL/UAVHumble22-validation/prospective_detection_independent_review01.json", "sha256": "0583f950a1557ece5988633d9c812f46b326f26c3bb15b4c5176303becd21a9e"},
  "adapter": {
    "shell": {"path": "/mnt/d/WSL/UAVHumble22-validation/formal48_dds_adapter01/formal48_guard_adapter01.sh", "sha256": "b1343b56e6effe488e3554b58fbae924aba26cfdc959e113d862ad9b14f9535b"},
    "python": {"path": "/mnt/d/WSL/UAVHumble22-validation/formal48_dds_adapter01/formal48_guard_adapter01.py", "sha256": "3973a0590981abf578cbd174371d13c82207c717669298b6d7769c14a242444e"},
    "reviewed_tools_sha256": "dbc9358db20d02e62c2963b868605b4e77f4d16a188f52c5e28e11e20f9f2d5a",
    "argv_prefix": [
      "bash", "/mnt/d/WSL/UAVHumble22-validation/formal48_dds_adapter01/formal48_guard_adapter01.sh",
      "--manifest-sha256", "ACTUAL_ADMISSION_FILE_BYTE_SHA",
      "--reviewed-tools-sha256", "dbc9358db20d02e62c2963b868605b4e77f4d16a188f52c5e28e11e20f9f2d5a"
    ],
    "resolutions": {}
  },
  "adapter_binding": {"path": "ACTUAL_ADAPTER_IDENTITY", "sha256": "ACTUAL_FILE_SHA"},
  "preflight_tools_sha256": "b8f75eccb143871130671a00ad5cf75fe0768e43bc46bb0a99c2586f207b0580",
  "audit_log": "FRESH_EXTERNAL_ABSOLUTE_AUDIT_JSONL"
}
```

`plans`直接复制 admission.plans；不得重算或重写原计划。新55合同和audit采用FORMAL55 kind；adapter identity仍按实际formal48支持的FORMAL54 kind，不能统一重命名。`admission.sha256`、argv的manifest-sha256是文件字节 SHA，不是admission内部manifest_sha256。`adapter_binding`在合同与CLI必须完全一致；adapter身份和独立canonical在CLI再次明确提供。fresh batch没有infrastructure-stop resolution，故`resolutions={}`；不能事前伪造诊断。

```bash
bash /mnt/d/WSL/UAVHumble22-validation/formal55_supplementary01/formal_supplementary_preflight.sh verify \
  --contract "$tracking_contract" --contract-sha256 "$tracking_contract_file_sha" \
  --manifest "$tracking_admission" \
  --reviewed-tools-sha256 "$tracking_supplement_reviewed_canonical" \
  --adapter-binding "$tracking_adapter_identity" --adapter-binding-sha256 "$tracking_identity_file_sha" \
  --adapter-reviewed-tools-sha256 dbc9358db20d02e62c2963b868605b4e77f4d16a188f52c5e28e11e20f9f2d5a
```

该CLI存在；verify只返回metadata-bindings验证结果，不写audit、不启动guard。任何拒绝均须保留stdout/stderr和退出码，不能以手改status覆盖。

## durable launch request：精确schema

原 durable54 无request-builder action，CLI只有describe/launch/worker/watch/stop。用实际对象构造以下精确schema并排他新建；不要把`--guard-command`之后的参数误归为serial参数。

```json
{
  "schema_version": 1,
  "kind": "FORMAL54_DURABLE_SERIAL_LAUNCH_REQUEST_NOT_ADMISSION",
  "created_utc": "ACTUAL_AWARE_UTC_BEFORE_LAUNCH",
  "python_executable": "ACTUAL_CANONICAL_PHYSICAL_PYTHON",
  "serial_entry": {"path": "/mnt/d/WSL/UAVHumble22-validation/formal54_serial_signal01/formal280_serial_guard54.py", "sha256": "2e0d15f735bb82b3f6a2d819620c4f8f03100b853e04485dddacdd4b426c1393"},
  "serial_description": {"path": "ACTUAL_SERIAL_DESCRIBE_STDOUT", "sha256": "ACTUAL_FILE_SHA"},
  "reviewed_serial_tools_sha256": "d7e1f4f2a8b8eccfcd99abd95c7a7a2e16dea8e128dc8eb97210b53db53b87b8",
  "manifest": {"path": "ACTUAL_SEALED_ADMISSION", "sha256": "ACTUAL_FILE_SHA"},
  "serial_output": "FRESH_ABSOLUTE_EXTERNAL_SERIAL_OUTPUT_DIRECTORY",
  "working_directory": "ACTUAL_EXISTING_CANONICAL_DIRECTORY",
  "guard_command": [
    "bash", "/mnt/d/WSL/UAVHumble22-validation/formal55_supplementary01/formal_supplementary_preflight.sh",
    "--contract", "ACTUAL_CONTRACT", "--contract-sha256", "ACTUAL_CONTRACT_FILE_SHA",
    "--reviewed-tools-sha256", "b8f75eccb143871130671a00ad5cf75fe0768e43bc46bb0a99c2586f207b0580",
    "--adapter-binding", "ACTUAL_ADAPTER_IDENTITY", "--adapter-binding-sha256", "ACTUAL_IDENTITY_FILE_SHA",
    "--adapter-reviewed-tools-sha256", "dbc9358db20d02e62c2963b868605b4e77f4d16a188f52c5e28e11e20f9f2d5a"
  ],
  "input_files": [
    {"path": "EVERY_ACTUAL_SMALL_INPUT_LISTED_BELOW", "sha256": "ACTUAL_FILE_SHA"}
  ]
}
```

真实 `input_files` 必须逐一枚举，下例占位项不能提交。只保存普通小metadata/code文件，不将bags/weights/目录当输入；列表顺序一旦写入则由registry保留，不再丢弃或重排。

- 新55实际supplement describe stdout；从其 `manifest.files` 对每个同级真实文件生成path/fileSHA（Python、shell、所有author/independent tests，包括新增guard-path tests）。如本次已有独立接受记录JSON，纳入其实际pin；不凭空制造新前置门。
- actual contract、adapter identity、actual Linux formal48 describe；identity的shell/Python，以及formal48实际同级test。
- contract.admission、两plans、protocol、selection、selection_basis、detection_review。
- protocol.producer_tools两个真实源文件；其独立review列出的author test；protocol.helper_source_hashes中的final-root小源码。
- admission.tool固定外部guard；实际外部owner41源与test；实际source-sidecar/核验记录如已用于本次启动决策。

durable自身canonical和serial六个manifest source/test由原工具另行自动核实；上述列表专门补足新55与supplement输入。不能因durable接受任意非空列表就省略真实新55 source pins。

owner与serial输出必须各自全新、父目录已存在、彼此不嵌套，且都在算法根和guard state以外。contract/audit/identity/protocol也按supplement规则外置。不要把任意“PASS”摘要当作input pin。

```bash
"$tracking_physical_python" -I -B /mnt/d/WSL/UAVHumble22-validation/formal54_durable_owner01/formal54_durable_owner.py launch \
  --request "$tracking_launch_request" --request-sha256 "$tracking_launch_request_file_sha" \
  --owner-directory "$tracking_owner_directory" \
  --reviewed-tools-sha256 f90b780da8d8020c6fec111fd40ac771a315afe82bdb532b8de9984309ce4b2f \
  --reviewed-serial-tools-sha256 d7e1f4f2a8b8eccfcd99abd95c7a7a2e16dea8e128dc8eb97210b53db53b87b8
```

原owner会生成registry，ACK前不会启动serial；完整ACK/registry SHA是后续watch/stop唯一身份依据。不得在没有actual ACK时声称后台实验已启动。

## 观察与停止边界

```bash
"$tracking_physical_python" -I -B /mnt/d/WSL/UAVHumble22-validation/formal54_durable_owner01/formal54_durable_owner.py watch \
  --owner-directory "$tracking_owner_directory" --registry-sha256 "$tracking_registry_file_sha" --once
```

持续watch可去掉`--once`并保留默认interval5。watch没有spawn/signal；关闭观察会话不停止owner/serial。需要停止时仅用原owner的显式`stop --signal INT|TERM`、相同owner/registry；等待原清理，无盲目PID/进程组kill。此卡不调用旧monitor的run包装器。

serial可串行完成最多280次既定guard调用。普通算法FAIL保留并继续；基础设施停止、来源/pin变化、空间门失败或未闭合证据都会保留STOP，不会自动重试或改种子。当前合同固定adapter.resolutions与audit链；发生新infrastructure-stop后，不得偷偷替换合同/新audit来继续，需要另行明确设计和审查的continuation，而不能伪造事前诊断。

完成判断是original guard pending=0及完整原闭合/owner终态证据。它不意味着全PASS、论文已写或全项目验收。后续仍按既定选源执行离线提取、独立label review、完整分母统计与交付；12条来源不是新飞行矩阵。

## 独立源审查与验证范围

独立审查逐项比较原54与新55生产diff，核Python3.10 AST，并从AST常量与实际六个OWN字节重建manifest；其canonical与作者实际Windows惰性describe完全一致。仅新增六文件manifest中的新test、FORMAL55身份、固定guard政策、`guard_source_binding()`以及原路径检查的单点替换；没有改原adapter argv、admission schema、全280分母、选槽或重试规则。

`guard_source_binding()`先调用不变的`checked()`核普通文件、规范绝对path与真实SHA，再允许legacy同根路径或精确fixed path+e64 SHA。该guard仍进input_pins并在exec前重核。实际guard模块的`__file__`/bytes验证仍由未改formal48执行。新增八测试覆盖生产Linux literal、原legacy全合同、fixed全合同+fake exec、同字节错路径、声明错SHA、实际改写后重算SHA、旧binding字节改动、audit后exec前字节改动；Windows物理文件fixture仅在测试内重定位常量，不冒充真实Linux读取。

| 当前新55证据 | SHA256 |
|---|---|
| formal_supplementary_preflight.py | 0953767edd2ba24e1996759ba5e806c146318d0c867953cdb5e22558ba6abf1f |
| test_formal55_guard_binding.py | aa149f223f46a97326f2fd9d89a04485a8163dbd40beeb7d23346d274098e634 |
| formal55_describe01.json | 98fb05595ffcd0aab9465fdc0fb3cbcaedcc1039cf469b09f02f8d3801bed55e |
| formal55_windows_tests01.json | 8e6f20fb45ad5e80717cbf73ae6060f18065aeba7509a3c5164cbc2085995144 |
| formal55_windows_tests01.log | 305d0aaf056ad16b9f0eaf1cef150100493015c85d138404dee399c6717aac44 |

以上证据位于`D:/WSL/UAVHumble22-validation/formal55_supplementary01/`。已核实际log终态为63/63 PASS（230.991s，exit0）且receipt前后六源码pins一致；这是作者实测，独立审查者未重跑。shell及原三测试与54逐字节相同。原54五OWN静态canonical仍为原已审b0c4f...，原Python SHA仍为144e5ed0efe97a4d75ef46b420ab2c38a5df8d2b629b15fe99647ebd389e4b83。

独立审查只读取Windows小源码/metadata，未import任何原工具、未执行WSL/native/guard、未读bag/model/VHD、未创建任何actual协议/identity/contract/request/admission/state。作者Windows describe是源身份证据；未来实际Linux describe/固定guard读取及真实formal连接仍按上文执行，不能重标现有Windows证据。未声称native运行、正式280开始或工程全部通过。
