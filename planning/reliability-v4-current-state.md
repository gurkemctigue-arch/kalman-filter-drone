# 当前工作交接（持续开发，非验收报告）

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
