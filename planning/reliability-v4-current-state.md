# 当前工作交接（持续开发，非验收报告）

最新15检查点：Humble15已冻结506源文件，manifest SHA256=`e28c7fe4fe4a22f693623eaa880d9f27e01a200d6f9055953b22463b63b056d7`，协议SHA仍`7264a01e823339aa8d4adfe006353a6b2184e36d4e359a40acdcd6daeeca847b`。相对14生产仅收尾helper与StreamDrainState两路径，另分类器/回归/文档变化。四包9.97s、真实module/ament隔离、1156项Linux检查（33.256s，OK，2平台/专属文档运行时跳过）均通过，冻结源前后不变。真实DDS四case已验证旧2s提前pause复现、候选晚到数据到齐后pause且严格末帧通过、缺target GT按原10s失败且不pause、rejected raw无需不存在的adapted。仅pause RPC为fixture，不冒充15实际飞行。14独立放弃说明为1FAIL11PENDING，原plan/slot不改。report_repair正串行15新两类clean，再新12核心、4安全、16扩展；280正式仍未登记执行。D可用约167.1GiB，逐槽继续容量预测。Windows专属防睡眠lease已续至2026-10-30T13:50:55.325010+00:00，PID28584，完成时只移除此专属lease使其自行释放。

更新：Humble14新两类clean20s已完成，source/native/录包/渲染/进程/末Clock同戳GT均通过。person导航208/208、距离/高度RMSE .305819/.262907m；car 217/217、.584973/.263610m。均未施加快门，因此surface遮挡项INCOMPLETE正常保留。新12格seed004计划摘要`f5175984e46f5583acf2720d8f5372bdfba852b2b0a3d184c66e3ac0f30f8289`的首槽person_velocity原终态FAIL、flight_exit1、infrastructure_stop=false：source6382三流、native、全部surface遮挡安全、465/465导航GT、有效覆盖.862366、距离/高RMSE .802373/.178762m与末端稳定均满足候选门，但收尾observer缺GT而`recording_closure`失败。其余11槽暂停，不覆盖旧记录。只读源码已确认旧warmup至多2秒且只等clock/raw，超时仍pause，可能在volatile GT订阅发现前停止生产；分类器又未读closure/完整性报告而漏报infra。report_repair修就绪判据及真实DDS烟测，github_publish修显式基础设施失败分类，两者稳定后统一新冻结。仍共享总10秒，不放宽最终Clock/真值/三流门。最近GitHub main已推进`d1b25003189790aae6f7a51b7316e8efabb571b1`，该检查点只报告14构建/隔离/测试通过。

14冻结检查点（以下记录早于上方两类clean及首核心槽结果）：2026-10-29，Humble14已完成源复制冻结、四包构建（10.2s）、真实模块/ament导入隔离及Linux全套检查：1148项，33.189s，OK（2项跳过，平台/专属文档运行时原因单列）。正在开始两类新clean与完整核心开发验证，尚不能声明14飞行通过。总505文件源manifest SHA256为`7d17744b9957233a80b1a168cb467d13a44e14a196665e916f5686d7cde55ce6`，协议SHA256为`7264a01e823339aa8d4adfe006353a6b2184e36d4e359a40acdcd6daeeca847b`。相对13在线变化恰为预期9路径；新增发布器生命周期及模型资源回归已包含。13另存`ABANDONED_DEVELOPMENT_PLAN_REASON.json`，记录3个已尝试与9个待执行槽及原文件hash，原计划/终态未改。B的嵌套遮挡物证据漏洞已最小修复，38项身份专项及独立复核通过；图表14项专项和端点小图目视检查通过。这些均不能代替新飞行证据。正式280次仍未登记或执行，留出1000–1009未使用。report_repair持唯一重窗口，串行完成两类clean和12格核心开发；轻量文档与只读源码工作可并行。最近公开main仍为`b2c46d6032d69f5c4dee5ce9289f75739b429934`，当前正在准备基于14全套检查的新开发检查点。

用户要求继续直到三阶段、重复实验与交付完成，且已授权GitHub推送。不要将此文件或少量探针当作项目已完成。最近公开开发commit为 `f965c4aa76d1c8bdad25f01795a31d176bd9dde0`；该提交后继续进行收尾修复与文档/图表流水线开发。

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

## 09 实测、GitHub 检查点与当前收尾工作

- 09 person新20s：启动门4.831wall秒真实PASS；native12.652源秒/25.305墙秒，runner总100.088墙秒；所有进程0、bag完整；原source evaluator raw/timing/adapted各3817，全配对、0缺证/0clock/frame失败，native PASS。nav/GT205/205，base_link距离/高度RMSE0.315299/0.260421m，末端settled=true（4.0/2.5s）。最后一条非网格nav真值bracket缺失单列unknown，主网格完整；model_origin高度censored不等于受控base_link失败。
- 同09 car新20s：启动门4.208墙秒PASS，native12.600源秒/25.200墙秒；runner99.947墙秒，全部进程0、bag/native/render PASS，nav/GT205/205，base_link距离/高度RMSE0.623901/0.255986m。但source INCOMPLETE：raw3819、timing/adapted3818。唯一缺口精确为全包最后raw seq22468，source38.740/receipt38.744；之前末配对source38.732，首0.572完全配对。原09car证据/判定保留，不能拼组件PASS为整体通过。
- 因果收尾修复：report正在新增独立ROS收尾probe，monitor终态后bag/ROS/PX4/GZ保持活着，先实际收Clock/raw/timing，pause world实际ACK后持续spin，要求Clock不前进、raw/diag/adapted计数稳定、末raw(sample/publication)确有对应diag；仅accepted=true才需对应adapted header，reject不等无效odom。短稳定窗、10s墙钟上限，逐观察存档；再关recorder和运行节点。全Clock/失败尾段照录照评、不裁尾、不豁免最后raw。先真实最小pub/sub验证乱序/延迟/reject及清理，再新10冻结和新两clean。
- 外部已备`D:/WSL/UAVHumble22-validation/freeze_humble10.sh`，尚未执行。10应从主树合入新的收尾生产源及当前全部离线工具，明确登记相对09的新增生产差异，不能再要求flight-critical与09相同。四包/隔离/全Linux后两clean及核心12/扩展16开发；候选开发seed4，不碰1000–1009。
- GitHub开发检查点已提交并push main：`f965c4aa76d1c8bdad25f01795a31d176bd9dde0`，远端ls-remote确认一致、提交后clean。主树1036 tests OK，9 Windows平台跳过，168.924s；289源码/配置开测前后不变，扫描PASS。Actions未确认（公共API出口限流、本机无gh），不能冒称CI PASS。
- 用户已收到更新工期：两类20s探针整次均约100wall秒，280正式按12–14小时估计，含开发矩阵/统计/交付按剩余16–24小时规划，依赖后续收尾和算法开发关口通过；并非无条件承诺。当前D空闲约175.79GiB、RAM空闲约14.04GiB；仍严格一次一个重任务。
- docx代理现实现新版报告/最终计划书流水线（按已读docx skill、docx-js），github代理实现新版图表PNG/PDF/SVG/CSV及来源manifest；均只写离线代码和轻量fixture，不造正式结果、不读heldout。新离线Python脚本须在OFFLINE_HELPERS，CJS文档源码单独记录hash。root负责后续真实验证/定标/冻结与整体推进。

## 接下来

1. 新10隔离构建/全套及两类真实CPU clean20s，验证pause ACK→完整尾流排空→关闭录包的真实效果。最小真实ROS五场景已经验证（延迟/乱序/reject/晚raw/缺diag），不替代新飞行。
2. 最终同一飞行源的两类×六组12格核心开发，固定seed004；两类stage1_velocity为预先指定的R0定标来源。短/长遮挡、显式重选、位置、多目标、中位/主动/多目标云台均实际验收。
3. 完成两类×八条件16格扩展开发；先固定性能门，再注册核心/扩展协议与replay参数/来源。保留故意压力工况的真实性能失败及任何新基础设施失败，不改旧槽。
4. 正式120核心+160扩展=280槽串行，每槽一次，完整分母；按当前实测整次耗时暂估12–14小时，开发诊断和交付另计。
5. 完成20条正式stage1_velocity同测量四法统计、检测/身份评价、图表/视频/Word/PDF/入口和GitHub同步。实际完成后才能最终汇报。

## 本次接续与离线定标工具

- 已重新核对main、三位活动代理与实际WSL进程，未重启或重复09任何槽。report继续独占重任务窗口；docx与github仅做离线文档/图表代码。
- 新`calibrate_estimator_replay_v4.py`从预指定seed004两类完整PROBE槽导出的已审计数组计算几何R均值。保留在线门控拒绝但独立几何有效的观测，去重不重复加权，读取完整FOLLOW→Clock尾，显式排除原因和采集ID；不混入R_pose、不拟合真值、无隐式jitter、不自动登记。已增加具名slot原run_config/bag_integrity小文件SHA与export原包路径绑定，8项专项通过，尚未对最终开发数据执行。
- 10两类clean20s的source/raw/timing/adapted均全部配对，原生起飞/录包/渲染/全部进程退出通过，汽车末端稳定。行人209网格中最后1个真值缺bracket（最后GT38.880、Clock38.908）导致settling如实右删失，原报告不改。
- 原因已定位为评价专用PosePublisher的30Hz采样边界。按官方精确tag源码（频率非正时每physics步发布）将16处GT插件设为-1；closure新增全部声明target/vehicle最终GT同Clock源戳闭合检查，仅用于离线录制，不馈送跟踪/控制/关联。真实最小ROS6场景验证晚GT等待、缺actor超时与清理。
- 新11四包/真实模块和ament隔离通过，Linux1087项测试通过（1项跳过，30.988s）；两类新clean20s正在串行验证。新版nav/summary已接控制命令变化率、画面中心/覆盖、图像到首跟踪命令仿真延迟、请求短遮挡内实际导航预测误差及真实error样本数；55项相关检查通过。图表与Word流水线已各自完成合成fixture验证，尚无正式数据/正式文档。

## 11 行人实测与节点关闭竞态

- 11person的source/raw/timing/adapted3733/3733/3733、native、bag、render均PASS；全部target/vehicle最后GT与Clock37.888同戳，205/205网格真值完整，base_link距离/高度RMSE约0.3148/0.2575m，稳定时间4.2/2.5s且维持至末端。真值每physics步采集修复有真实证据。
- 严格ROS子进程审计发现state_estimator在launch发SIGINT后、rclpy._take_subscription.take_message报pybind RuntimeError并exit1；原11失败保留，car未跑，不得以launch主进程0或物理正常覆盖。
- 原因是默认rclpy信号处理异步关闭Context而executor仍取消息；report正统一自有节点生命周期为SignalHandlerOptions.NO、只设停止请求、同Context显式executor、先停executor/worker再destroy node最后shutdown context。运行期callback RuntimeError继续抛，不扩大例外吞错。需真实高频ROS SIGINT负载验证，再新12冻结和两clean，随后固定seed004核心12格。
- 为长批量任务启动临时Windows防睡眠请求，不改系统电源方案。专属进程PID28584；外部记录`D:/WSL/UAVHumble22-validation/keep_project_awake_process.json`。租约最长30小时；任务完成后移除同目录`keep_project_awake_lease.json`使进程自行释放请求。不要结束用户其他应用。
- docx正在接真实检测审核小工件，并准备专用Linux Node24官方SHA下载与现有Windows Word隐藏独立实例转PDF；尚未实际渲染正式Word/PDF。github正在实现只读开发关口组装器，必须经现有validator核验真实12/16格后才发布；不会代写登记或执行正式种子。

## 12 双类 clean 闭合与进入核心开发

- 12四包/真实module与ament隔离通过，Linux1095项检查完成（1项跳过，32.625s）；生产main+真实ROS高频fixture的22项生命周期行为全部通过，涵盖重复SIGINT/SIGTERM、真实RuntimeError仍退出1并清理、monitor正常主动完成。无扩大RuntimeError吞错。
- 12person clean20s：runner0；全部8 ROS子进程正常退出，infra.stop=false且reasons=[]；raw/timing/adapted3787全部配对，source/native/bag/render均PASS。最后Clock38.428与target/vehicle GT同戳，导航207/207真值100%；base_link距离/高度RMSE0.3262/0.2583m，稳定时间4.3/2.6s且到末端。
- 12car clean20s：runner0；全部ROS子进程正常退出，infra.stop=false且reasons=[]；raw/timing/adapted3844全部配对，source/native/bag/render均PASS。最后Clock39.000与target/vehicle GT同戳，导航210/210真值100%；base_link距离/高度RMSE0.6059/0.2633m，稳定时间2.6/2.4s且到末端。
- 两clean没有设计遮挡，surface的INCOMPLETE不能改为完整安全PASS；它们只关闭基础设施与无遮挡物理跟随关口。report现按既定授权创建同源seed004两类×六组12格不可变PROBE计划，随后逐槽执行；正式1000–1009仍未使用。
- 新图表、文档、检测审核接入、定标和实际开发关口生成器已完成对应fixture/只读review；main准备下一开发checkpoint。Linux Node24已安装至专属/root/uav_document_tools（官方SHA下载，纯JS docx实测可用），Word隐藏独立实例转PDF脚本就绪，尚未生成正式文档。

## 新公开检查点与首个完整遮挡任务

- 已提交并推送`b2c46d6032d69f5c4dee5ce9289f75739b429934`，远端main经ls-remote核对一致，发布时工作树clean，60个已审查路径，未上传results/权重/私有runtime manifest，敏感扫描和diffcheck通过。未确认Actions状态。
- 12核心PROBE计划位于`results/frozen_fullplan_v4_humble12/reliability_v4_humble12_probe_seed004_matrix/plan.json`，摘要`fa33dfd4fbf837edb4c1a8e0f8f736e29e34518b47857612b1524607672160e8`。首槽`person_stage1_velocity_seed004`实际45s+短/长遮挡+显式重选完成，flight0、source6339三流全配对、native/surface PASS、457/457真值、nav有效覆盖0.8621444、base_link距离/高度RMSE0.81966945/0.17127929m、稳定时间35.1/32.1s且到末端、末Clock63.948全部GT同戳、无残留或runtime错误。
- 此槽原终态仍为INFRASTRUCTURE_ERROR：旧`research_failures.py`只认acceptance.result/result，误把三个实际合法的evaluation_status报告识别为MISSING_OR_INVALID。完整原记录保留，剩余11槽没有推进，不将该infra_stop=true槽强行充开发readiness或定标来源。
- 已定方案：精确修纯离线分类器识别全部实际source/native/navigation/physical/legacy report schema与状态，未知或缺证仍停止。将确实仅飞行后使用的research_failures模块显式列OFFLINE_HELPERS。新13冻结/构建/隔离/全suite，证明所有实际飞行关键源与12一致后无需重飞两clean；前瞻新建同seed004两类六组12格，定标固定其两个stage1_velocity。旧12首槽和未执行槽另存放弃说明，绝不改plan/原终态。
- 原计划两项安全触发不在核心/扩展矩阵：auto_unique三个候选的歧义悬停、locked_target刻意几何多解的歧义。github代理正在给出最终同源两类×两情形共4条额外开发安全probe的严格命令，独立于120/160分母，不读取留出。

## 13 新核心开发与真实汇总接线

- 13四包/隔离完成，Linux1115项检查通过（2项跳过，33.727s）。`freeze_validation/origin_humble12_source_classification.json`明确记录238个飞行关键源/世界/模型全部与12相同，协议也相同；差异仅为具名离线工具和编排。两skip另存`unittest_skip_explanation.json`，分别因Linux环境无Windows PowerShell、普通flight/test PATH没有独立安装的Node/docx，未声称真实文档渲染完成。
- 新13固定seed004核心12格计划SHA256：`fb4b797400ffe01c9bfc111dc816cfbdef01368d68aeeabb276d3f4680ab4c20`。首`person_stage1_velocity_seed004`已完成：flight0、infra_stop=false、source6334三流全部配对、native/surface PASS，nav/GT461/461、有效覆盖0.8590021692、base_link距离/高度RMSE0.8613766429/0.1746204915m、稳定35.2/32.2s且至末端、全部GT与最终Clock63.896同戳、无残留。短窗同track/UUID恢复0.116s；长遮挡悬停/制动及禁止自行恢复、显式重选后持续跟踪通过。原终态EVALUATION_PENDING仅因性能门尚未登记，记录不可改。
- root使用当前summary源码只读新计划，生成`results/development_summary_v4_humble13_snapshot01`（1.0s，1终态/1运行/10待）。首槽无report issues；绝对距离/高度p95为2.3584190565/0.2741565643m，8项操作层恢复/显式确认指标已真实接入，显式确认0.096s。位置模式命令变化在velocity槽为null符合模式定义。此开发快照不能充正式结果、定标或最终门。
- summary/report各21项专项通过，新增恢复完整分母/未知/右删失、绝对p95与位置命令变化。新版图表14项专项通过；真实图仍待数据，夹具图不能充实证。代理正在整理歧义安全与检测审核的精确执行卡。
- 已前瞻固定最终可视交付选源：`planning/reliability-v4-delivery-selections.json`规定正式seed1000两类六组12条完整演示、两类stage1_velocity同seed检测审核。失败/缺片不得替换成功种子，完整机会与排除保留；检测仅是独立审核完全可见的仿真子集。
- 首完整任务实际227.44墙秒，正式280据此约18小时，剩余总体估算已向用户改为22–30小时，后续按真实吞吐更新。D约169.5GiB空闲；首槽bag458.42MiB、telemetry35.83MiB，后续逐组计量容量并为临时spool保留余量。C仅约0.7GiB、E约9.65GiB，不能假设其他盘可容纳正式数据。旧bag/失败证据不删。

## 13 实质问题、旁路诊断与14候选

- 第2槽person_stage1_position完成但真实距离性能不足：RMSE1.4536511m，末误差0.8332m且距离稳定右删失；高度RMSE0.2398641m、source/native/surface均通过。根因包括参考发生器仅调节`desired-previous_reference`而没有闭合实际机位误差，造成纯位置内环恒速滞后；每轴1m参考领先量也限制重选后追赶。root已改主树为`desired-vehicle.position`反馈、仍积分previous，六类配置与ROS默认每轴领先量改为[2,2,.5]；速度/加速度/时效/验收门不变。消息级无效输入出口加portable.reset。纯控制12项、消息边界10项通过，两代理独立审查无阻断；真实飞行仍待14。详见`docs/V4_POSITION_REFERENCE_CONTROL.md`。
- 第3槽person_stage2_crossing飞行完整但stop失败，原终态INFRASTRUCTURE_ERROR：Stage2Motion自定义`_publishers`与rclpy注册列表冲突，stop误向String发布器发送Twist。其他ROS节点正常退出。主树改名`_velocity_publishers`，真实Humble两类别×SIGINT/SIGTERM共4项验证退出0、三路末命令为零、无traceback；冻结13不改。
- 原13三槽和剩余9个PENDING均保留。未在原trial补写评价，而是新建矩阵diagnostics旁路读取原包，并核原trial/plan/slot前后SHA一致。第一次暴露离线模型root硬编码旧PX4路径；主树两个helper现显式解析STAGE1_PX4_ROOT、记录实际SDF路径/SHA并拒绝缺声明资源fallback，真实gz展开与11项相关回归通过。诊断revision01漏复制依赖mesh失败也保留；revision02复制完整模型后完成。
- 13crossing的revision02诊断：source/native通过；surface与指定个体持续跟踪失败，但禁止自动换人/预测时效/长丢悬停均通过。独立物理身份固定REQUEST到完整Clock共466格，correct288/wrong0/unknown178，known=.618026；导航465/465真值、valid349/465=.750538，距离/高度RMSE1.212474/.169422m，末段稳定删失。后段HOLD来自框重叠的保守导航拒绝，非时效门失效。路径`results/frozen_fullplan_v4_humble13/reliability_v4_humble13_probe_seed004_matrix/diagnostics/person_stage2_crossing_seed004_models_root_revision02/`。
- 两项前瞻14候选已分别声明边界：A核心crossing改一次18s quintic车道交换后保持，18s来自匹配原首半sin峰横速17.905s取整，名义22s完成；全程/末端门不改，原周期压力失败不改，不冒充在线几何改进。主树轨迹6检查通过，DRAFT协议加完整时间线，见`docs/V4_MULTI_TARGET_SCENARIO.md`。B仅离线物理身份拟用完整独立静态mesh的全光学深度范围证明所选目标严格前于全部重叠actor；需完整全部actor/exact source-time几何/无快门等专门证据，缺任何条件仍unknown。github代理实现B，原MOT可见子集和runtime保护不动。
- root实际看过原13四帧开发视频接触表`results/development_visual_v4_humble13_crossing01/contact_sheet.png`：所选近处行人在约58s的HOLD画面中可见，背景两人框重叠；此图仅视觉诊断，视频相对时刻不是精确源戳证明。原视频未变。
- 最终视频依赖已在Humble安装：ffmpeg/ffprobe包`7:4.4.2-0ubuntu0.22.04.1`，dpkg delta仅新增ffmpeg，无原包升级/移除。真实4帧H264编码/探测通过，安装来源、二进制SHA和样片归档`results/freeze_validation/ffmpeg_install01/`。当前尚未freeze14/正式飞行；等待B专项完成后统一新冻结、四包/隔离/Linux及两类/12格实测。
