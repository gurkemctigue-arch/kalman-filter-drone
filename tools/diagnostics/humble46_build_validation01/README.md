# Humble46：构建通过、原生全套验证失败

本快照保存真实源码版本 `de89a6696d60a113929c97bab775dc2258ef4d01`
的来源组装、独审发布、prepare/copy及维护小型原件。46冻结根为
`/root/uav_tracking_fullplan_v4_humble46`，完整来源1123项、classified来源295项。
快照是在冻结后加入main的后续交付资料，不进入既有46冻结根。

来源组装、构建及失败验证均已闭合：source-only实际退出0；source review经过独审后仅改变
原两项status字段；prepare为PASS、207.180660802秒，copy为PASS、297.054841482秒。
两者均保留原300秒预算、direct child退出0、无残留及实际来源绑定。
build实际PASS、98.857365998秒，保留四包构建、隔离、FastCDR/CDR原件与环境。
原validate为FAILED、direct child退出2、动作158.260090078秒；原suite共1789项，
1 failure、5 skips，用时99.268秒，summary为FAIL/returncode=1。原来源与历史capsule
前后不变，无signal、无残留。失败为
`test_car_surface_registration.CarSurfaceRegistrationTests.test_legacy_trial_exact_hash_and_no_mutated_default_fields`
在61行的固定hash断言；完整原断言和suite footer已保存，不改写为通过。
尚未组装或发布46 runtime candidate，没有新飞行，不重试原46验证。

目录内容：

- `source/`：原PENDING/FINAL source review、capsule、历史结果摘要、source发布和实际组装回执。
- `independent/`：实际adapter/maps独审、PENDING/source publisher独审及原失败与五项skip核对。
- `external_tools/`：本次窄adapter、真实maps/pins、原生执行与维护脚本的原字节副本。
- `actions/prepare/`、`actions/copy/`、`actions/build/`、`actions/validate/`：已闭合动作的原终态、日志、预检查及关闭回执。
- `freeze_validation/`：实际source manifest、FINAL source review、构建环境、colcon日志、隔离/CDR原件及失败summary/unittest原日志。
- `maintenance/ntfs/`：六个历史文件透明压缩的实际idle、执行JSONL、whole-call结果及独审。
- `maintenance/git/`：不带`-d`的增量Git对象打包前清单、实际结果、来源绑定计时与独审。

NTFS独审记录六文件实际分配量减少323,141,632字节；同窗口磁盘净空闲变化
310,968,320字节是另一项观察，两者不相加、不外推未来压缩率、不折减正式容量预算。
原whole-call结果中的待review状态及capacity_credit=0按原字节保留，后续独审另件引用。

Git维护保留原2593个Git文件（含2568个loose对象），仅新增pack/idx/rev；实际
`fsck --full`退出0，八个dangling blob原样保留。未改原HEAD/refs/index/config、
源码、generic工具或验收阈值。原生来源绑定一次测得39.795510264秒，286项
物理字节与Git blob比较及来源绑定与原prepare完全相同；copy通过以其实际终态为据。

健康构建来源仍43。44原suite失败、45原build/validate PASS（1767项、5跳过）和
45原core中止（1 PASS、1 INFRASTRUCTURE_ERROR、10 PENDING、owner mismatch）
保留于原capsule与历史摘要，不计入46新批次通过数。正式实验仍为0/280。

五项skip的完整测试名与原因保存在原summary及
`independent/validate_failure_and_five_skips01.json`；原log、summary与源码skip contract
五项完全一致：1项Windows PowerShell fixture、3项真实Windows共享语义、1项缺少
Node.js/npm docx的渲染器门。它们不能解释或抵消那一项failure。

`manifest.json`逐件登记60份原件的来源路径、大小及SHA；复制前后重新核对原件，
`SHA256SUMS`同时绑定本地说明及manifest。`.gitattributes`禁止本目录文本转换，
保留原日志换行及空白。本快照不包含bag、模型权重、完整telemetry或health负载，
快照作者没有启动WSL、构建、测试或飞行。
