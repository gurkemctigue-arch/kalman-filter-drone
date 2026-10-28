# 当前执行接续记录

## 接续优先状态（2026-10-27 UTC 11:56）

- 无活动仿真、录制或正式 guard。原 session80898 已退出2；正式127/166终态（85 PASS、42 FAIL），余39 PENDING均阶段三。下一槽为 `fullplan_v3_stage23_s3_person_gimbal_active_seed000`。不要轮询旧会话或重飞终态。
- `/root/freeze_isolation` 独占原 stage3 midpoint seed000 bag/ULog只读审计，结束前禁止启动probe/仿真/重分析。已设解压2300MiB硬预算、至少1GiB宿主余量；当前C约4.12GiB、D231GiB。
- 用户已授权关闭其他应用，已关闭豆包、Steam、两项非项目GradleDaemon Java；最新Windows可用13.37GiB。不再请求用户释放内存，也不能声称内存已修复仅status超时。
- 审计结束后运行独立 `stage3_midpoint` probe：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_link_stability_probe_windows.ps1 -AuditSuffix v4 -Profile stage3_midpoint`。独立名/audit均未使用，不计166，不改冻结/安全阈值/RTF。
- 主版diagnostic driver修复循环变量覆盖试验名的问题，用 `trial_name` 绑定session/start event/flight_evidence；原stage2 driver_source.py及原SHA保留。仅诊断元数据修正，flight argv原样；当前plan-only运行成功。
- 新增 `scripts/run_guarded_full_plan_windows.ps1`，PS语法已通过，尚未运行；使用相对 `--study-output results/full_plan_research_v3`、v3精确SHA、进程级防睡眠，默认plan-only。链路probe复核后可用全新audit v7恢复39，不要使用旧full_plan_windows脚本的绝对output。
- 主版交付补丁已有实测：metric12、report22、Word门14、node --check通过，Windows全套604=599PASS+5SKIP/exit0。详见 `docs/V3_DELIVERY_VALIDATION.md`。冻结未改。
- `stage1_audit` 正仅做小文件静态审查，区分研究终态齐备与系统工程验收；不运行重任务。余下仍有主offline166、工程16、supp16、指标/图/最终可视化和MD+DOCX/PDF、cleanup独立真实probe。

## v7 守卫最新覆盖（2026-10-27 UTC 15:06）

- 独立 stage3 midpoint probe v4 已 exit0：flight/ROS/native observer均完成，official ledger unchanged=true、diagnostic_capture_complete=true、idle_after_probe=true。它没有复现中止；ROS FOLLOW窗口 raw status最大完成接收间隔约1.096s，raw odom约0.120s，不能据此宣称根因修复。
- 原冻结 stage3 `person_gimbal_active_seed000` 已正常飞行收尾，评价报告齐全但 flight FAIL、gimbal FAIL_OR_INCOMPLETE；guard stop=false并继续。
- 原冻结 stage3 `person_gimbal_midpoint_seed001` 在仿真50.5s再次触发 `status_stale`（status age2.344>2.000，odom age0.085，armed/OFFBOARD/failsafe=false），没有 flight/gimbal报告；v7 guard exit2并在剩余37条前停止。详见 `docs/V3_STAGE3_PERSON_MIDPOINT_SEED001_STATUS_STALE_DIAGNOSIS.md`。
- 同参数独立 seed001 probe 已正常完成：status FOLLOW窗口最大约1.096s，odom约0.114s，observer/原生Gazebo捕获/清理均完整，official ledger unchanged=true；但资源采样仍有分页，不能据此宣称根因修复。详见同一诊断文档。
- 不能直接启动新formal guard或重飞该同名槽。下一步应使用全新 guard v8逐槽恢复剩余37条，并继续保留v7；若新异常再次出现，立即停止并保留证据。
- stage1_audit已修订主README、`docs/STAGE1_ACCEPTANCE.md`、`docs/THREE_STAGE_STATUS.md`：历史 stage1_final_v2 4/4单次演示与当前v3 100槽66P/34F严格区分；v7新增2个阶段三FAIL后当前主总计85P/44F/37PENDING，offline仍0/166。

## v8 守卫最新覆盖（2026-10-27 UTC 15:37）

- v8 已尝试6个原阶段三槽：active seed001、midpoint/active seed002、midpoint/active seed003 均正常生成 flight/gimbal 报告并 PASS；midpoint seed004 飞行本身 `follow_duration_reached`、monitor0、bag完整，但两个评价器读取临时 SQLite 时均报 `SQLite error (11): database disk image is malformed`，无评价报告，guard按基础设施异常停止，剩31 PENDING。
- 当前正式终态由 v7 的129条增至135条：约90 PASS、45 FAIL（v8 midpoint seed004为新增评价基础设施FAIL），31 PENDING；offline仍0/166。v8审计目录 `results/fullplan_v3_guarded_continuation_v8`，不可覆盖或重试同名槽。
- `/root/seed004_bag_audit` 正在独占该槽 bag/metadata/压缩帧只读审计，未运行仿真；审计结束前不要启动v9。若原始压缩帧可独立解码，应仅形成衍生诊断，不覆盖正式FAIL或补造原评价。

## 最新覆盖状态（2026-10-27 UTC 11:07，资源释放后恢复）

**UTC11:09后覆盖：单槽session25803已exit0，seed006安全PASS/guard stopfalse/errors空，现117/166终态=77PASS/40FAIL。剩余49由唯一root session80898、全新audit `results/fullplan_v3_guarded_continuation_v6`继续逐槽运行，当前seed007。不得再轮询25803或另起仿真。** 独立probe完整审查见 `docs/INDEPENDENT_LINK_PROBE_2026_10_27.md`；host最低可用6.50GiB但11/31样本有分页读取，GZ1442JSON完整/无回退，RTF中位.500016，不能用成功probe推断原故障根因。research_pipeline获授权仅修改主版report/renderer/tests/doc，补supp16完整性+来源SHA门和合并mAP输出；飞行期间不得执行测试，勿改guard/classifier/supplement。

**UTC11:29覆盖：唯一活动仍为session80898/audit v6；已123/166终态=82PASS/41FAIL，stage23=16PASS/7FAIL/1RUNNING_FLIGHT/42PENDING。carcrossing006–009四条全PASS、personparallel与personambiguity均PASS；carparallel普通评分FAIL（recorded_occlusions_pass=false，短窗有效depthgap .8s>预测.75s并LOST/HOVER；没有基础设施异常，guard继续），正在carambiguity。** root基于用户已有关闭权限，核实并终止两个非本项目GradleDaemon Java进程13220/61344，未关闭Code/其他文档；后续可用内存约7–8.4GiB。

**UTC11:35覆盖：仍为唯一session80898/audit v6，阶段二26项全终态=19安全PASS/7FAIL，主126/166=85PASS/41FAIL。carambiguity与person/car auto_unique均PASS，无新增infra停止。阶段三40项开始，当前 `fullplan_v3_stage23_s3_person_gimbal_midpoint_seed000`，stage23=19P/7F/1RUNNING_FLIGHT/39PENDING；主offline仍0/166。** Windows空闲内存现约9–10GiB。阶段二仅飞行/安全已全部尝试，不能称物理身份/状态精度研究全部完成。

**UTC11:37后最高优先覆盖：session80898已exit2，audit v6正确STOP，无活动仿真。主127/166终态=85PASS/42FAIL，39PENDING全部阶段三；首stage3 person midpoint seed000因status_stale ABORT。supervisor wallmono2331.182791，status age2.316>2s/lastmono2328.866957，而odom age.167<.5/lastmono2331.015624；ROS51.752、adapterheader51.736不能推断真实物理推进。原stage3 flight/gimbal评分均未生成，原FAIL/缺失保留。此时内存充足，不能继续称腾内存已消除问题。** freeze_isolation独占原bag+ULog只读时序审计，现允许解包/过滤，但不要同时开仿真或其它重分析；root下一步要等它结束，再跑同参数独立stage3probe。

主版probe新增 `--profile stage3_midpoint`（原 `stage2_crossing`保留），新独立名 `diagnostic_v3_stage3_person_midpoint_link_20261027_v1`，external `results/link_stability_probe_stage3_20261027_v1`，**尚未执行**。Windows调用将为 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_link_stability_probe_windows.ps1 -AuditSuffix v4 -Profile stage3_midpoint`；driver/host用全新v4文件，脚本会持awake并隐藏子窗口。profile参数逐项匹配原run_config（stage3/person/seed0/speed.5344421851525049/320/2threads/midpoint/auto_unique/initialnone/min2/parallel/distance5.0/height3/occlusion+reselect/43s/RTF.5/timeout300）。root已保存已完成stage2probe准确driver源码到其external/driver_source.py并核对SHA ceec5f0178853f89196b241a4d1ff633df3ff7e78b463d137151471f9134a56f。新probe将自动归档自身源码。

已趁无仿真窗口完成最新交付验证：metric12/12、report22/22、Node Wordgate14/14、Node语法PASS；完整Windows suite604项=599PASS+5SKIP，session42535exit0（12.337s）。随后只改诊断probe profile并通过Python编译/PS语法及plan-only，不改生产/冻结。

PX4源码新证据：Commander状态正常500ms仿真时钟发布或状态变更即发，RTF.5约1wall秒；rate_limit5是上限不是保证5Hz。DDSwriter BEST_EFFORT，generated dds_topics.h先orb_copy后prepare_output_stream，后者失败可静默丢该更新（错误打印被注释），**只是候选路径无运行计数证实**。同一XRCE client的低频status可能缺单条而odom新，也可能共同短暂停顿后高频odom先恢复，不可武断二选一。DDS输出timestamp会加动态session time_offset（每>1s同步），禁止把rawstatus相邻timestamp差直接当PX4源周期或减ROSsim/宿主epoch。原ULog `/root/PX4-Autopilot/build/px4_sitl_default/rootfs/log/2026-10-27/11_34_50.ulg`可对照源uORB但需确认logger限流/dropout。继续绝不放宽冻结安全门限或改RTF掩盖。

交付主版补丁已准备、**尚未执行测试**：report/renderer新增offline166、supp16与metric-supplement绑定，Word contract_version2复核6份小JSON当前SHA；嵌入完整分组指标，合并mAP绑定review_file_sha256且只GT>0类计mAP分母；逐任务配置核对。metric补表修null物理报告crash、空几何任务IDSW伪0，增加同track/UUID短恢复率/时间及条件分母、缺失/不适用分列；冻结原summary旧IDSW聚合保持历史但最终报告抑制。agent均已交付schema与必要新tests，尚未测试。空闲后必须至少执行 `python -B -m unittest discover -s tests -p test_metric_supplement.py -v`、`python -B -m unittest discover -s tests -p test_full_plan_report.py -v`、`node --check scripts/render_research_docx.cjs`、`node tests/test_report_docx_gate.cjs`；最终再全suite，不能声称补丁已验证。runbook已添加新的 `--offline-manifest --supplement-manifest --metric-supplement` 参数。

用户已经保存并关闭部分应用，随后明确授权本代理关闭应用。root已关闭全部Doubao进程，并调用Steam正常退出；没有关闭Code、Java、Word或本项目窗口。可用内存由5.48GiB升至约8–9GiB，飞行时约7GiB。采样中仍可能有分页读取，不能称全程无分页，也不能据此证明旧超时根因。

**当前唯一活动正式会话：root session25803，外部audit `results/fullplan_v3_guarded_continuation_v5`，仅 `--max-new-flights 1`，正在运行原PENDING `fullplan_v3_stage23_s2_car_crossing_locked_seed006`。此前116/166终态(76PASS/40FAIL)保持，剩余50包括本次运行。勿启动第二个仿真。** guard/classifier/supplement仍为原哈希，飞行期间禁止修改这些文件。

独立稳定性probe已经完整结束：`diagnostic_v3_car_crossing_memory_relief_20261027_v2`，不计166，原冻结seed5相同参数；root session98345 exit0。外部证据 `results/link_stability_probe_20261027_v2`、host `results/host_link_stability_probe_20261027_v3.jsonl`。flight/monitor/bag/ROS/PX4/Gazebo均0，独立ROSobserver0，Linux与native观察器按SIGINT收尾(-2)。`diagnostic_capture_complete=true`、`idle_after_probe=true`、`official_ledger_unchanged=true`、无残留/cleanup错误，native1442行412KB。ROS158聚合、0drop/0error/0limit，writer最大1.504ms；FOLLOW最大完成callback gap：rawodom65.884ms、converted65.149ms、status1.062s、clock40.069ms，未再ABORT。这只是本次未复现，不能写根因已修复或完整安全评价PASS。

主版新增 `scripts/observe_ros_link.py`，4窄单测+Linux4秒空ROS启动exit0/5聚合已验证，证据 `results/ros_link_observer_empty_20261027_1901`。新增只读诊断协调 `scripts/run_link_stability_probe.py` 与Windows wrapper。首次Windows wrapper因PS5 UTF8无BOM中文字面路径失败、未启动Linuxprobe，保留driver v1；首次Linuxprobe因为继承TMPDIR到D而被observer拒绝，未起飞，保留external v1与driver v2。已改动态Unicode路径和显式ext4 `/tmp`，实际完成的是driver v3/external v2。全部历史保留。不要重新运行同名probe；wrapper外部audit后缀和PythonNAME/defaultaudit都是一次性名字。

partial116可视化已交付 `results/验收检查点_116.html`，核验JSON同名；166正式=76PASS40FAIL50PENDING，offline0/166，117录制卡含1额外探针。33专项PASS，3044处文件引用/1975独立目标均存在，旧总览SHA不变。此快照不随后续自动刷新，不是最终验收。

接下来：等session25803完成及guard核验；如无基础设施异常，新的外部audit v6继续剩余原PENDING49，不重跑任何终态。随后主offline166、summarize、独立工程16及supp16、全166失败分类/图表/固定seed视频/最终MD+DOCXPDF、独立cleanup新冻结及两probe。精确命令见 `docs/FULLPLAN_V3_DELIVERY_COMMANDS.md`。freeze_isolation正在小文件审查probe；research_pipeline只读核对最终交付管线；不允许重操作与飞行并行。主版完整suite此前581=576P/5SKIP，之后新增dashboard/observer窄测均已PASS，最终全suite仍需空闲窗口。

## 最新覆盖状态（2026-10-27，v3 恢复前）

**最新优先：116/166终态（76PASS/40FAIL），50PENDING，无活动仿真/录制/评价。session2363在carcrossingseed005再次ABORT后exit2，guard v4正确STOP；不要继续轮询或启动正式pending。原car003和005均保留基础设施FAIL/缺安全评分，car000/001/002/004四份可评分FAIL，行人crossing10PASS。observer session96344已自然完成（601.989s），不能以它保留旧WSL实例；当前WSL又自然退出/重启过。**

**seed005证据：mono612.226688 ABORT，odom wall1.384>.5/status2.405>2，ROSnow35.752/adapter重打header35.664；后者是两节点缓存ROSclock，不能证明Gazebo只进.088sim。observer gap mono611.803776→615.188702=3.384927s，abort实际执行在该gap内部，不能称整VM连续停顿；observer写D盘可能本身阻塞。该记录范围pswp/oom0，内存/IO PSI不变，CPU等待增多，根因仍未定。**

**当前阻碍是宿主资源：18:40后Available约1.2–1.5GB，commit约59.6/68.7GB，有分页读；WindowsCode42进程私有提交总11.82GiB，Java2.68、Edge2.64、豆包2.21。不能终止不属于本项目且可能含未保存工作的应用。root已用async提问，请用户保存关闭不用的应用以腾6–8GB/或指定范围，尚无回复；这不是再次询问是否继续项目。继续独立诊断/材料，暂不烧正式50。**

活跃代理：freeze_isolation只读宿主资源/原时间窗，research_pipeline做外部只读ROS时序observer（rawPX4/status、clock、convertedodom、phase，1Hz聚合写ext4，待实际验证）及GZstats命令；stage1_audit在主版生成明确partial116的新视觉验收检查点HTML，不转码/解bag/YOLO，不碰最终验收总览_v3.html。Harmonic没有gz stats命令；有效native统计为 gz topic --echo --topic /world/stage2_flight/stats --json-output --duration 120，需同partition/IP。root需等工具与资源就绪后先独立诊断probe，不能改冻结门限/RTF规避或重跑原槽。后续正式guard新audit目录继续原50；仍需主offline166+独立16+补充+最终分类/统计/视频/WordPDF+cleanup新冻结。

**最新UTC10:20：115/166终态（76PASS/39FAIL），单槽carcrossingseed004已完成，评分FAIL但guard0/stopfalse/errors[]/infra无原因，未再次ABORT。单槽session6556已结束，后续51由活动root session2363、外部audit results/fullplan_v3_guarded_continuation_v4 顺序恢复；旧52479不可轮询。原seed003不重跑。观察截至309样本：最大采样间隔1.014982347s，MemAvailable最小13,946,044KiB，pswpin/out0、oom_kill0，仅说明该新试验未复现，不能归因原seed003。观察session96344共600s仍自然运行，勿杀；它是只读/proc观察，不是仿真。**

**最新：主114/166终态（76PASS/38FAIL），stage23为行人crossing10PASS、汽车crossingseed000–002三份可评分FAIL、seed003一份监督器ABORTED基础设施FAIL。guard v2已正确stop，旧session52479 exit2，不能再轮询。52PENDING。直接触发：ROS日志odom wall age3.508>.5、status4.542>2，ROS now38.148/odomstamp37.896，外部根因未知；全部进程有序退出/bag0，冻结master未启动评价器，不能伪造评分。详见 docs/V3_CAR_CROSSING_SEED003_RESOURCE_DIAGNOSIS.md。停机当前资源健康，WSL曾自然退出后新实例，旧boot日志无足够根因证据，不声称排除OOM/睡眠。**

**当前活动：root session6556 正以全新外部审计 results/fullplan_v3_guarded_continuation_v3 仅执行一个原PENDING汽车seed004（--max-new-flights 1）。read-only资源观察 session96344 正运行600s，输出 results/host_observer_v3_car004.jsonl；其小型冒烟6条记录完整退出0。新增主版 scripts/watch_sim_resources.py 每秒读小型/proc文件，无控制/信号/资源修改，路径不含uav_tracking_，不会触发守卫进程误检。禁止并行第二仿真/重测试/bag。等单槽结束+guard评估+观察数据核对后，才能全新audit继续余51。**

新增工程guard13项及相关25项专项全PASS；主版完整suite581=576PASS/5SKIP。源码guard/classifier/supplement仍原SHA。full166分类工具由stage1_audit补齐所有小来源前后指纹，尚未最终执行；默认拒绝非全终态。新增 carseed000 小报告独立诊断说明和full166guide已进入runbook。seed003缺安全评分不能由后续主离线流程伪造，该流程只另算物理身份/状态/瞬态指标。

**UTC09:58检查点：主110/166终态（76PASS/34FAIL），阶段二行人crossing seed000至009共10/10安全PASS，独立物理身份离线仍待。当前session52479持续正常运行同一外部guard v2，已转入s2_car_crossing_locked_seed000；stage23剩余56未终态（1运行/55PENDING）。所有新增已完成槽位guard stop=false；不得启动第二仿真。**

**更新（UTC09:31后）：首个阶段二 s2_person_crossing_locked_seed000 已真实 PASS，guard 返回0、assessment.stop=false、errors为空、bag退出0、解码clock15385，旧100行未变。当前主进度101/166（67PASS/34FAIL），剩余65已由活动root session52479在外部审计 results/fullplan_v3_guarded_continuation_v2 顺序执行；不要启动第二个调度/仿真。该会话使用Windows进程内SetThreadExecutionState防睡眠，结束自动恢复。首次单槽session65605已正常结束。完整Windows suite568=563PASS/5SKIP；仅修了supplement的可移植路径测试断言。guard/classifier/scripts/run_full_plan_supplement.py 在当前会话全程不可改。独立16 guard+12夹具已准备但未测试，freeze正静态审查，待研究空闲窗口。**

阶段一全100条轻量分类已完成：66 SCORED_PASS / 33 SCORED_FAIL / 1 CONFIRMED_INFRASTRUCTURE_FAILURE，原66PASS/34FAIL保持。见 docs/V3_STAGE1_FAILURE_TAXONOMY_100.md 与 results/stage1_failure_taxonomy_v3_100/；33行为失败不推断深层原因，100条在线精度评价均仍待后处理。不要将安全行为或UUID保持当作完整跟随成功。

主 v3 为 100/166 终态，66 PASS / 34 FAIL，阶段二三尚余 66 PENDING；无活动仿真、录制或离线评价。旧 session54739 已结束。seed08 诊断已完成：压缩帧未结束，独立 libzstd 解码可通过 SQLite 完整性检查，原生 ROS reader 在 D 盘副本重现丢失末尾 128 KiB；写入端根因未定。原始结果、压缩包和冻结源码均未改。证据见 docs/V3_BAG_INFRASTRUCTURE_AUDIT.md。

外部逐槽 guard 与 classifier 已经独立审查，专项测试 classifier23、cleanup26、guard15 全部通过。Windows 完整测试 568 项中 562 PASS / 1 FAIL / 5 SKIP，唯一失败是 supplement 测试将 POSIX 路径硬编码；research_pipeline 正修正测试断言，不改生产代码。完整复验通过后，先以全新外部审计目录 fullplan_v3_guarded_continuation_v1 执行一个阶段二槽，再核验 guard outcome 后继续剩余 65。冻结源、原始 output 相对文本与 plan SHA 均保持不变；旧 100 个终态不得重飞或改写。

当前主副本已安装 node docx，node --check 和 require.resolve 通过，node_modules 已加入 .gitignore；最终结果 DOCX/PDF 尚待全部研究结束后生成和逐页检查。后续顺序仍为剩余真实飞行、主离线166、独立16及补充、统计图/演示视频/验收页、中文报告与Word/PDF、独立cleanup新冻结探针，不能以启动后台进程交差。

用户授权完成三个阶段全部实现、真实实验、统计、可视化与最终计划书；不要重新询问是否继续。不能用代码或后台进程启动代替完成。失败保留，不重跑同名试验。

## 当前时点（2026-10-27 北京时间）

**最新优先状态（北京时间约16:56）：v3 主研究已完成100/166次：velocity80=51 PASS/29 FAIL，position20=15 PASS/5 FAIL；剩余stage23 66 PENDING。当前没有仿真/评估/编排进程，session54739已结束。car position seed08 的评估日志报SQLite error11数据库损坏，原基础设施classifier漏检；不是普通算法失败。为阻止继续stage23，root在最后car seed09飞行期间仅SIGSTOP总入口PID334，待position子PID75352全部完成且成为zombie后向334发送TERM/CONT终止；最后car09 PASS，录包完整，无当前飞行被打断。不能把此暂停当作用户暂停或权限障碍；诊断后继续完成授权工作。**

- 正式冻结根 `/root/uav_tracking_fullplan_v3`，D盘 `results/frozen_fullplan_v3`，prefix=`fullplan_v3`，plan canonical SHA=`58f509351f6f2efba6da33ea394feff0e81f10b5fde03ba2866de2ab5232af28`。四包构建/导入隔离/531测试已通过。冻结源绝不可修改。
- 恢复参数必须从该root用相对 `--output results/full_plan_research_v3`；初始plan存了stage23相对路径，Windows wrapper使用绝对output导致digest冲突。未改plan，改用原root内入口恢复。
- 独立 `v3_bag_finalization_probe_car_position_seed02` 已完整录包PASS收尾（bag0/metadata/zstd齐，约26s压缩），不计166。正式carpos02 PASS、carpos03普通FAIL且bag0/metadata齐；180s收尾修复未再因timeout杀bag。
- carpos08：bag0、metadata和压缩文件存在，飞行正常；offline_evaluation.log仅1537字节，SQLite malformed traceback，evaluation_returncode1且无offline报告，原classifier却stopfalse。原FAIL/日志/压缩文件保留，不重试同名槽位。
- `stage1_audit` 当前独占重诊断工作：先编写main脚本，再在idle窗口校验原zstd/SQLite，区分原bag与ext4/DrvFS临时解压问题，SHA前后、不得修原文件。已授权其实际诊断，root不要并行重测试/bag/构建。C盘原仅约5GB，先检查容量再决定ext4解压（单bag解压可能近4GB）。
- `freeze_isolation` 当前仅改main classifier和外部逐槽guard+夹具，不动frozen；增加缺报告且evaluator异常/SQLite损坏识别。诊断未结束前不执行tests/build。目标在外部条件修复后保留v3已100尝试，未改frozen源码/资源时仅恢复66 PENDING，外部guard每次调用冻结master `--phase flights --stop-after 1`并检查异常，普通验收FAIL继续，基础设施FAIL立即停。
- 已有 `docs/V3_FAILURE_DIAGNOSIS_DRAFT.md`：扫描完整80velocity及深查3FAIL+3PASS的小JSON/telemetry，真实可用性失败+正确保护；短遮挡恢复age .808超过.75，重选后连续门控拒绝导致测量冻结，再LOST。不能把bbox/conf高或UUID未变称为成功；拒绝的更深原因未证明，非全部166结论。
- `research_pipeline` 已准备 `docs/FULLPLAN_V3_DELIVERY_COMMANDS.md` 与 `scripts/render_research_docx.cjs`，尚未执行node/生成最终工件。root已完整读取docx skill并向用户宣布使用。最终MD+sources→DOCX→PDF逐页渲染检查；现有计划书DOCX/PDF保留。后续最终报告应链接失败诊断。
- 新cleanup main工具已参数化5个显式v3输入，需166flight+166offline+16extended+16supplement终态及SHA关联。25夹具未测试；全部研究结束后先同步mutable `/root/uav_tracking_project` 再独立 `/root/uav_tracking_fullplan_cleanup_v3`，不可改v3源。两真实probe阶段一8节点、阶段三multi9节点仍待。
- 下一步顺序：完成损坏审计→验证main classifier/guard→原v3仅恢复66 PENDING→serial主offline166→独立extended16→supplement16→统计图表/浏览器视频/dashboard/中文MD与Word/PDF→独立cleanup freeze/probes→最终文档与SHA归档。每约60秒简短commentary，所有FAIL保留、未知/删失/缺失不填零。
- v2已在88次后因45s bag finalize边界两次早停（80velocity62P18F+position8=4P4F，carpos02/03基础设施FAIL），旧数据保留不并入v3。下文v2活动session信息全部是历史。

以下条目为旧时点历史，与以上最新状态冲突时以上和实际清单优先。

**最新优先状态（UTC约11:00）：主166仍在活动长运行session=48386，正式速度80槽已全部结束（62 PASS/18 FAIL，均为普通验收失败，基础设施未早停），入口已自动进入位置兼容20槽；position子清单已有seed00 PASS、seed01 RUNNING。不得重启第二个仿真，不得在飞行中读bag/构建/批量复制/重测试。**

- 主版停止信号补丁由freeze代理交付：ROS Popen显式stdin=DEVNULL，初始SIGINT仅发launch PID，其他服务仍killpg；既有TERM/KILL兜底不变。8项信号mock PASS，seed1PASS/3SKIP；冻结v2 runner SHA未变。真实清理未验证，166+16完成后另建新冻结根/新prefix做两个独立probe。
- 中文最终报告生成器补丁14项纯JSON测试PASS，stage2代理独立复审CLEAR。最终还需无仿真窗口全suite。
- 三代理继续轻量工作：freeze准备cleanup probe；research核对原计划指标覆盖与后处理；stage2只读审计两条car失败及身份指标边界。均不得在当前实验期间启动重任务或改冻结数据。
- root实际查看新car adaptive的frame_00101.jpg（sim20.1正常FOLLOW、清楚的汽车框）及frame_00301.jpg（sim60.1 HOLD/LOST、汽车远离且有检测框）。不能凭框仍可见推定关联/三维门控失败的具体原因。

- `/root/uav_tracking_fullplan_v2` 独立四包构建、module/ament隔离、Linux492项全部PASS；Windows同suite487PASS/5SKIP。
- 新results链接D盘 `results/frozen_fullplan_v2`，环境清单已捕捉（Ubuntu24.04/Jazzy、ROS签名ready=true）。166计划已生成且绑定源码与prereg，canonicalSHA `2791685e042c6253b8715da939dfcb53193e7d7b211540a7ad2734b86630c7e2`。
- v2源码在任何飞行前tar归档 `results/frozen_fullplan_v2/source_snapshot.tar.gz`，SHA `d5fcda436a325f5d6aaede22572c95d071691e865aca229936729c1de3988b62`；`freeze_validation/source_archive.json`另存来源与测试证据。
- base最终SHA `bfd78659ff3d75f2f2bde343d53bf8a0d3c9529b7f0e630f000c2fd53ecddabf`；stage2最终 `a1a705f4d45c6cd2eb8597368a9bf4eb2f1d4a6e0fe9e937ba97e769fc16159e`。evaluation_revision=3，正式冻结源码不能再改。
- 原car/raw bag三次独立读取均完成，最后revision3真实重评PASS，原FAIL/revision2FAIL和SHA未变；新报告/audit另存原trial。715后续active、260tracking controls、持续13.012s，真实receipt回退0/invalid0，mixed回退2仅诊断。freeze代理独立核验9份受保护文件actual SHA前后一致。
- 当前已去掉StopAfter并执行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_full_plan_windows.ps1 -Phase all -Resume`。速度80已终态62 PASS/18 FAIL；position20正在执行，之后按冻结顺序进入stage23 66及serial offline。按子清单和主summary读实时进度，不用旧快照猜。
- 真正退出清理尚有局限：前两条在monitor正常结束/先停bag后，ros group SIGINT再经launch转发，6节点exit-2、3个destroy_node KeyboardInterrupt（不再是旧already-called）。bridge/detector clean；首条旧PID无残留、浅层无新core但未追WSL crash handler全部输出。严格flight/eval均0/PASS、infra stopfalse；不可称“真实干净退出已验证”。主doc POST_FREEZE_SHUTDOWN_REVISION已记录，冻结源/log未改，暂不为after-stop SIGINT重开第三主研究。
- 速度矩阵普通失败均保留且未触发基础设施早停；全部166飞行结束后才serial offline。另16用同冻结根shared lock单独执行，不并行。最终报告/图表/视频/HTML/文档仍待，不能后台启动交差。
- 4份主版操作文档已由freeze更新为上述事实，THREE_STAGE_STATUS/full-plan-completion亦完成；主README已更新。冻结根不跟随这些主版文档再同步。验收页已重建，40份历史工程条目及新166完整槽，历史superseded说明生效。
- research代理仅在Windows改最终中文报告工具/tests/doc补失败率展示，10纯JSON定向tests原先PASS；stage2独立review指出阶段2旧saved failure_rate把RUNNING/UNKNOWN当非PASS，正在改为按真实逐flight终态Wilson再加回归。该交付工具不回同步冻结根，最终生成前须定向复验，最终全suite待无仿真时。绘图CLI默认v1，必须显式--summary results/frozen_fullplan_v2/full_plan_research_v2/summary.json --output results/frozen_fullplan_v2/full_plan_figures。
- UTC19:29容量C5.18GiB、D322.84GiB；旧每flight约.42GiB，182总量空间足够。所有新bag/tmp/ROS日志/ULog均用D专用路径。

以下保留旧调查过程供追溯；与以上最新状态冲突时，以上及实际动态清单优先。

- 主代码在 Windows `D:\基于yolo和卡尔曼滤波`，同步 Linux `/root/uav_tracking_project`。一次只能有一个仿真；飞行期间不跑离线 YOLO、bag 解压、批量复制、构建或重型测试。
- 旧冻结 `/root/uav_tracking_fullplan_v1` 的 `results` 链接到 D 盘 `results/frozen_fullplan_v1`。首8真实飞行全部结束：7原PASS、1原FAIL，无基础设施早停，无活动仿真/95099会话已exit0。
- v1唯一原FAIL是car/raw seed0，原bag已实际核实：确认前旧LOST seq25896、新MEASURED确认seq25900均为op49.62，原评价丢失reader顺序。revision2另存后715条均新UUIDactive，但新加hybrid-time chronology导致仍FAIL：seq28883 PRED(header55.240,recv55.224)→28887 MEAS(header55.100,recv55.224)，及31760 PRED(60.640,60.624)→31762 MEAS(60.500,60.624)，两次合法16ms混合时刻回退。
- 已决定evaluation_revision3：保留max(header,received)原派生time/时长和门限，seq唯一决定窗口/先后；坏state/UUID一律保留FAIL；仅真实received /clock有效且不回退作为硬时序检查，混合time回退仅诊断。research代理拥有base/tests、新doc3及prereg说明，stage2代理拥有其两文件，freeze代理只读独立复审。未冻结v2，未起新仿真。
- 原FAIL、revision2 FAIL、两份reader/chronology审计全部保留于旧car/raw目录，不覆盖；research二次bag读取均exit0且释放独占。revision2精确源码已在任何新sync前从Linux归档到Windows results/evaluation_revision2_source/，manifest含5份文件完整SHA。当前Linux仍base6016/stage2 5a14，Windows正改revision3。
- v1源码归档 `results/frozen_fullplan_v1/source_snapshot.tar.gz`，SHA256 `9d5d4091530f88c8ed9d6c65afe2ec1e470f3e72b02e283e0860de35ecabef97`。原计划SHA `fcf23b3e5d7ced2330cc0dfabd709dd835a8e0b35a5b6b83ce9f6c93d74fd24e`。`superseded.json`另存原因，158个未执行项不能填成完成。
- revision2最终Windows完整suite484项：479PASS/5SKIP；base39、stage2 33定向PASS，独立review17PASS。随后真实bag发现上述chronology假设问题，故这些不是revision3最终测试，需最终重跑。
- 主版8个真实飞行节点已修幂等退出（try_shutdown），detector线程join未改，6测试覆盖48分支PASS；冻结v1未改。真实退出清理验证留待v2飞行。
- 新默认路径/prefix已改v2，prereg已加study_revision。尚未创建 `/root/uav_tracking_fullplan_v2`，尚未开始新166。

## 紧接着做

此节1–3已实际完成；现从第4项继续监测活动session9406，不能再次freeze既有v2或重复同名试验。

1. 等revision3 base/stage2和独立review完成，统一 `wsl -e bash /mnt/d/基于yolo和卡尔曼滤波/scripts/wsl_sync_build.sh`。窗口无仿真，research代理再读同一v1 rawbag，另存 `offline_evaluation_revision3.json` 及审计；保留原FAIL、revision2 FAIL和全部SHA。临时解压务必经旧v1 run_research_session.sh放D盘。
2. Windows完整tests并更新实际计数；freeze新根 `/root/uav_tracking_fullplan_v2`、专用全新D目录 `results/frozen_fullplan_v2`。freeze做独立colcon、module/ament路径隔离、Linux全tests、源码SHA。研究前8旧目录约每次.42GiB，D盘323GiB余量足够182次，C盘5.16GiB避免解压。
3. 新环境清单放新frozenresults根 `environment_manifest_before_formal.json`；生成新166 plan（fullplan_v2/output full_plan_research_v2），检查源hash，先新8飞行验证后resume整个166。v1八条不纳入新分母、不复用。
4. Windows长运行入口 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_full_plan_windows.ps1 -Phase all -Resume -StopAfter 8`，默认已v2。它保持系统醒着、不改电源方案。首8通过后去掉StopAfter恢复全部，持续监测到完成，不以后台启动交付。
5. 全部flight后master串行offline身份/online/dynamics。额外16另跑 `scripts/run_extended_engineering.py`（默认extended_engineering_v2、单seed工程，不计主166）。两个入口共锁，不能并行。
6. 汇总/绘图/失败率/配对统计；更新README/统一状态/最终研究报告/计划书，完整归档bag/video/源snapshot并核hash，重建dashboard，实际看图/视频。科学负结果保留。

## 已有工程验收

阶段一两类×velocity/position四份final_v2严格PASS。阶段二parallel/crossing/auto_unique两类通过，汽车歧义v5严格PASS（前4FAIL保留）。阶段三两类active/midpoint物理与飞行通过。联合person active v2、car active v3分别stage2安全18PASS + gimbal物理13PASS。

联合car v3独立216任务机会95正确/0错误/36无fresh/85unknown，动态图GT299/299；online位置RMSE .473032m、速度 .211498m/s、active .847635；视觉179/215=.832558，center9.21491px，179源图首command mean .174726sim秒/p95 .252；距离/高度初始与重选都right-censored，不能声称已持续稳定。root已真实看两类联合24张源图，记录 `results/stage23_joint_root_visual_review.json`。

## 存储与交付工具

PX4 rootfs/log已完整移到D盘 `results/px4_ulog_archive_20261027`，原路径是symlink，无数据删除。C盘约5.7GB，D盘300GB以上。研究session把TMPDIR和ROS_LOG_DIR也指向frozenresults/runtime。

主版dashboard已支持完整166/离线166和扩展16、历史失败、新6组图表/PDF/CSV（27测试PASS）。报告生成器 `scripts/build_full_plan_report.py`（7测试PASS）只读小JSON，不预写成功。查看 `docs/FULL_PLAN_REPORT_GENERATOR.md`。最终绘图 `reports/plot_full_plan_study.py` 只消费真实summary。

计划书docx/pdf已交付并逐页看过5页。若改FINAL_PLAN，按docx技能重新生成/渲染并实际看全部页。主Linux旧大results已rsync归D，未来v2直接写D无需再次复制全部大bag。不要编辑冻结源码，修复后必须新root/新prefix；明确仅后处理修订可另存报告，不覆盖历史。
