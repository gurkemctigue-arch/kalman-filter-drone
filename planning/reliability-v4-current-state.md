# 当前工作交接（持续开发，非验收报告）

用户要求继续直到三阶段、重复实验与交付完成，且已授权GitHub推送。不要将此文件或少量探针当作项目已完成。最近公开commit为 `6cba40534ecdf884741dc7e837b10ef81f4fc540`；本轮后续修改尚未提交。

## 固定边界

- 一次只运行一个仿真、录包重分析或大型构建。开发种子不得使用1000–1009。
- v3冻结、182条历史主/扩展试验及全部失败不改。Humble03/04冻结和失败不覆盖。
- odom0.50s、目标观测0.60s、预测0.75s、马氏9.21、LOST显式重选和Offboard后reset保护保持。
- 120正式槽仍DRAFT/性能门未注册，尚未执行。仅同测量四法离线比较，不能称四法导航闭环因果比较。

## 新证据

- Humble03汽车原生起飞成功，但原生FILE zstd包缺尾，原试验证据不完整。独立完整解压的诊断副本仅定位用途，不改判。
- 新`recording_archive.py`：ext4无压缩录制→关闭/SQLite integrity/count→标准zstd完整frame→独立SHA往返→Humble原生全量read/hash→发布。原生实测40852条通过。
- Humble04 `/root/uav_tracking_fullplan_v4_humble04`：四包/导入隔离/901 Linux测试通过，结果位于`results/frozen_fullplan_v4_humble04`。
- `reliability_v4_humble04_car_clean_seed00`：原始bag 41174条，完整性/source_clock/native_startup PASS；导航覆盖100%，GT202/203，KF位置RMSE0.09645m；base_link距离/高度全程RMSE0.62951/0.26644m，尾10秒0.01892/0.00447m。无遮挡，最后GT bracket缺失、严格settling右删失，不能报完整工程PASS。
- 同冻结person探针在source5.652s ABORTED：status源戳5.152s，正常源龄0.500s，但receipt wall龄2.010>2.000；odom龄0.014s。bag完整/source_clock PASS，native FAIL。未进入检测（n640/2仅开发配置），不自动重跑同槽。

## 已落地待新冻结

- native起飞40源秒+独立180墙秒STEADY timer，双起点/elapsed/原因独立审计。
- supervisor状态`source_sim`采用原1秒源龄/0.05秒未来界，另10墙秒停流（ROS tick检查，不称独立steady）；重复/非法/过旧/回退不刷新、回退锁止。legacy默认保持receipt_wall。105项组合与45项runner专项通过。
- 主协议已指向Humble22磁库登记；实际Humble PX4 ELF `6cf784c1cb4de2945b4291aa9391a2301c78315a1462ef3f51f541e119fd7ce7`。
- 导航schema2记录R_geometry/R_pose/R_total、准确pose时刻/6×6/杆臂、TF、质量null/标记、processing/publication/header/output身份，输出数值齐全。
- 新四法pure core、bag exporter、online导航数值复现与native-state对应审计已纯fixture集成（133项组合）；真实schema2录包导出待执行。compound同一diag保留原seq，task→measurement→output子序；state header/publication/native delivery分开。
- bag reader opt-in `preserve_clock=True`，新navigation评价保留完整clock-only尾段，历史默认保持。旧04报告不可覆盖，另名新版评价。
- README/v3历史scope已澄清；新增便携Python3.10/3.12全unittest CI，test extra含PyYAML/matplotlib、APT zstd，不做ROS/SITL冒称验收。

## 最新验证与当前并行任务

- Gazebo原始回调已精确映射到`/usr/lib/wsl/lib/libd3d12core.so`，偏移`0x2edb10`。仅服务停止2/2崩溃；预加载D3D12一次退出、一次hang/KILL，不采纳。显式llvmpipe实际RGB-D发帧后，服务/SIGINT关闭均exit0，实际maps含swrast/LLVM15且不含WSL D3D12。新增Gazebo进程专用三项环境变量与实际ELF/mapping核验；完整CPU飞行性能尚待06验证。
- 严格`shutdown_guard`已落地：只有已关闭context、精确已知pybind错误且traceback来自rclpy._take_subscription才处理；未知/运行中/不相关错误重抛。新增ROS子节点非零退出分类，父launch退出0不能掩盖子失败。
- 04car真实导出02通过：`results/development_offline_v4_humble04_car_seed00_export02`，204测量/1220输出，online float64与全部native-state逐一核对PASS。输出01的164差异完整保留；原因是消息声明的float32 covariance/age。修复只按schema显式量化后精确比较，1ULP改动仍拒绝，float64容差不变。TargetState.msg也绑定hash。该开发证据不改变04飞行失败判定。
- 05已完成四包构建和导入隔离；969项Linux测试仅1个旧fixture ERROR：假PID731没有mock新render capture接口。未启动仿真、未改05冻结。`report_repair`仅修主树test_simulation_seed fixture，专项通过后新建06。
- `report_repair`持有唯一重窗口：06以05完整已冻源码为输入，仅合入上述fixture修订并记录唯一差异hash；不等待正在编写的纯离线gate。06重新四包/隔离/全套测试后，串行person n320/2/d5、car s640/4/d9 CPU clean20s。每次独立检查录包、源时钟、native startup、实际渲染库、全部进程退出、导航物理误差和末尾GT bracket。新基础设施/连续性失败先定位，不自动重试同槽。
- `github_publish`实现purecore/CLI真实证据gate，绑定arrays与同目录online/native/truth审计、源码/消息和完整条数；无证据仍pending。仅OFFLINE_HELPERS，后续单独绑定评价revision，无需因工具变化重飞。准备GitHub开发检查点，但尚未提交。
- `docx_pdf`轻量更新两份过时状态文档，并静态审计原计划实验/指标/材料与120矩阵覆盖；不运行重任务、不修改协议或代码。

## Humble06 实测与后续启动修复

- 06四包/真实module及ament隔离/969项Linux测试全部通过（测试21.20s）。与05的453个源文件相比，仅`tests/test_simulation_seed.py`的夹具修订不同，审计为`results/frozen_fullplan_v4_humble06/freeze_validation/origin_humble05.json`；05未改。
- 06person clean20s实际完成native起飞（12.300源秒/24.600墙钟秒），17.600s REQUEST_OFFBOARD，17.952s FOLLOW。实际CPU库/录包/全部进程退出PASS，Gazebo与ROS均exit0；总墙钟96.475s，FOLLOW观测20.248源秒/40.505墙钟秒，实测RTF0.49989。
- 独立native PASS；导航203/203真值/状态100%，base_link距离/高度RMSE0.31775/0.25737m，KF位置/速度RMSE0.25692/0.08090；末端距离/高度均settled=true，稳定时间4.2/2.4s。末Clock38.208、GT38.196、odom38.204、nav/phase38.200，当前person没有04car最后网格缺GT的问题。
- source-clock仍INCOMPLETE：3765 raw，3757 timing/adapted；缺的8条精确位于首次adapter诊断前0.572–0.636s，首诊断0.644。之后含尾段三元组全部健康，无clock/frame回退或连续性FAIL。保留此缺证，不裁切评分起点、不宣称工程PASS。
- report暂停在car前，正修实际ROS/DDS endpoint就绪等待：unpause前确认原生odom发布、真正adapter订阅、odom/timing发布与recorder订阅/QoS均就绪，结构化存档。旧camera topiclist就绪不足以证明adapter discovery。修复后新07冻结和新名两clean，不重试06同槽。
- root完成独立160扩展编排初版及9项专项，连原47项共56测试通过（47.356s），默认DRAFT阻断正式。github代理正补正式扩展对真实core计划、注册UTC、首条core飞行前冻结及实际开发readiness的绑定。docx代理正修离线检测配置与cache/review来源，不启动重推理。
- 原计划覆盖审计与详细执行顺序在`planning/reliability-v4-remaining-deliverables.md`、`planning/reliability-v4-remaining-execution.md`。120核心之外需最终Humble八工况×两类×十次=160独立扩展，均未登记/未运行。

## 07 启动门与真实 export03 更新

- 已完成真实paused图诊断：/clock在0时 native raw DDS publisher、adapter订阅/发布、rosbag2_recorder订阅均能建立，约1–2s发现，所有测试进程已清理。新门可在unpause前检查真实endpoint/QoS/GID/adapter服务callback和DDS matched counts，无循环依赖；稳定1s加guard0.5s，45s墙钟失败上限。
- 07以06冻结加明确8文件构建，四包/模块/ament隔离及979 Linux测试通过。新person在unpause前失败：rclpy独立Context配默认global executor触发AttributeError；原结果和ext4 spool保留，未起飞、不重试07，car未跑。report将显式同Context SingleThreadedExecutor修复collector/fixture，先真实最小spin/预期超时检查，再新08冻结、四包/全套与两clean。当前重窗口归report。
- 新离线payload审计曾被docx独立review找到漏洞：只绑时间/顺序未绑measurement内容。现exporter将除循环audit链接外的全部arrays canonical digest写入三份sidecar，gate逐一核对；位置/R/身份/task/output/truth等篡改均拒。
- root用真实04car原包生成全新`results/development_offline_v4_humble04_car_seed00_export03`，6.2s，exit0、204测量/1220输出online/native均PASS；01/02和04原件不动。随后Windows轻量JSON独立集成`gate_integration/integration_report.json` PASS：正确原03接纳，position+100/R/task UUID/truth变化拒绝，formal模式拒development，旧02缺新版来源也拒。receipt为专用DEVELOPMENT_ONLY kind，pure core不能凭它升格正式矩阵。
- github新扩展绑定已稳定：61项原/新runner测试、7种压力安全缺证否定、71项replay/export专项通过。core正式如存在扩展协议，须在freeze前REGISTERED/UTC/16开发格真实gate；extension正式必`--reference-plan`绑真实core文件SHA/digest、40参考ID、flight/model/runtime/protocol、首条core前登记。压力算法FAIL可保留，但长丢失安全/时钟/起飞/录包缺证不能当readiness。尚未真正登记任何正式协议。
- docx新增`scripts/summarize_reliability_v4.py`，14项纯JSON专项通过：完整120/160分母、缺失/删失、trial块配对bootstrap、all-finite与both-PASS、JSON/CSV/HTML。仅离线helper，github需在OFFLINE_HELPERS排除其flight-critical身份。
- root候选定标规则写于`planning/reliability-v4-calibration-policy-draft.md`：候选物理1.0m/.40m、nav.80/truth.99/identity.75+zero-wrong、既有末端3s稳定；R0用每类最终开发融合前全部独立有效geometry R平均，候选Q1/P0diag(1,1,1,4,4,4)/v0=0/EMA.35。该文件不是REGISTERED配置，正式未运行。

## 08/09 的公开 API 收敛

- 08四包/导入隔离/979 Linux测试PASS（21.653s），仅collector与fixture相对07不同；真实空图烟测验证显式executor正常spin/预期timeout存FAIL证据/销毁。但08person在unpause前因Humble Subscription没有`get_publisher_count`失败，旧槽保留，car仍未跑。
- root要求停止引入ctypes/私有handle解引用兼容层。新09只用公开API：raw侧`Node.count_publishers`准确标记discovered（不是RMW match），真实Trigger callback证明adapter已构造并spin，输出pub的`get_subscription_count`证明原生支持的实际匹配；外部实际endpoint GID/类型/QoS兼容与连续稳定/guard仍保持。原source-clock逐条完整配对不豁免、不改评分起点。
- report已接收收敛指令，先实际最小pub/sub/Trigger验证所有公开API、QoS兼容/不兼容与清理，然后从08加入明确修订新09冻结、构建/全套与两clean。一次重窗口仍由report管理。
- summary离线工具已稳定并加进OFFLINE_HELPERS；github候选74文件约1.26MB，未stage/commit，等待collector稳定与全源检查。root已轻量review扩展登记/真实core引用、安全边界及summary schema，未发现额外阻塞。

## 接下来

1. 新06隔离构建/全套及两类真实CPU clean20s，验证已修复的基础设施确实适用于飞行。
2. 完成真实离线证据gate与专项，更新公开开发检查点；不能用PASS布尔自证审计通过。
3. 短/长遮挡与显式重选、位置、多目标、中位/主动/多目标云台；完成两类别×六组12格开发矩阵并核对原计划扩展条件。
4. 最终两类×六组完整开发关口后注册性能门与replay R0/Q/P0/EMA/common gate，正式120槽串行，每槽一次保留失败。120槽按本机实测约8–10小时，仅串行正式运行，开发诊断和交付另计。
5. 完成20条正式stage1_velocity条件离线四法统计、最终图表/视频/Word/PDF/入口和GitHub同步，实际完成后才能最终汇报。
