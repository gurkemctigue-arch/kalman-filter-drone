# 独立软件管线时延基准：观测设计（完整基准未实现、未运行）

本基准是补充独立实验，不缩小原设计目标，不替代280次正式研究、飞行验收或历史strict UNKNOWN；不测物理曝光、PX4执行效果或真实闭环时延。
实际消息类型是`TrackingCommand`，当前源码没有`FollowCommand`类型；终点限定为`Px4AdapterNode._on_command`实际回调入口。
指标暂名`bench_rgbd_callback_to_adapter_callback_monotonic_ns`，只统计完整可验证因果链；不通过共享header、相同payload、最近消息或RTF推定因果。

1. **输入、环境和端点**
从已保存、停止写入且SHA绑定的开发录制回放原RGB、对齐Depth、CameraInfo、TF、车辆Odometry、/clock及实际所需phase/selection；仅选择输入话题，不回放旧算法输出或原fmu流。
使用冻结54原权重、参数、算法节点与每节点原SingleThreadedExecutor；新具名独立ROS_DOMAIN_ID、本机通信和外部输出根，保留回放顺序、速率、完整时长及其声明。
不启动SITL、Gazebo、FlightSupervisor或arm流程；Controller的TrackingCommand在本bench直达Adapter，明确排除正式飞行中的Supervisor路径。
Adapter原fmu输入全部remap到无发布者的bench输入，OffboardControlMode、TrajectorySetpoint及其他输出显式remap到bench sink；启动后核实际resolved topics/graph，禁止真实`/fmu/in`写出。
不改变Adapter门控来伪造飞行就绪；终点在command接收，完全不依赖arming、Offboard或setpoint生效。
每次RGB/Depth回调入口记录`time.monotonic_ns()`和外部接收对象token；对worker真正选择的两对象，定义`t0=max(rgb_callback_enter_ns, depth_callback_enter_ns)`，即该组在Detector回调层均已到达。
不得按相同stamp自行重配深度；`InferenceSnapshot.rgb/depth`实际对象决定组合，未选中/重复/缺同步输入另记，Python对象ID必须带生命周期token防复用。
`t1`是对应TrackingCommand进入Adapter回调的monotonic时刻，`latency=t1-t0`；全部节点同一Linux实例，记录boot_id、时钟实现/分辨率并验证不倒退。

2. **冻结文件不改写的外部wrapper观测点**
在构造节点前仅于bench进程装饰原方法、Node创建的回调及publisher；原函数恰调用一次，原参数/返回值/异常/消息体不改，源码、配置、权重原SHA前后复核。
Detector依据：`detector_node.py:386,427`接收Depth/RGB；`:484,494`构造并提交实际Snapshot；`inference_worker.py:30,37`把同一job交给worker。
包装submit返回值和`_infer_snapshot(snapshot)`建立`接收对象→snapshot token→worker job token`；worker线程上下文标记实际发出的frame/observation，忙时拒绝、早退、异常均留记录。
Detector发布依据：`detector_node.py:889,904,908`实际发布TargetObservationArray及逐候选；只跟踪原配置真正启用的Estimator订阅路径，禁止重复投递另一条路径。
Estimator依据：`state_estimator_node.py:230,248,261`保留实际frame/source对象；`:756,769`调用NavigationEstimator.update，`navigation_estimator.py:172,173`仅在接受后提交测量时间。
包装实际update返回的`accepted`，按任务UUID/track维护外部“最近接受输入token”；拒绝测量不能刷新token，identity/reset/clear须同步清除观测关联。
`state_estimator_node.py:883,885,890,910`由真实project结果构造并发布navigation TargetState；publisher观测原输出对象与实际接受token，预测输出继续引用其旧接受来源。
若另行测surface控制路径，必须跟踪Tracker实际接受的Detection对象；不能拿`_last_source`当最后接受目标测量。该路径未有完整hook前保持不可评价。
Controller依据：`controller_node.py:125,126`回调保存实际TargetState对象；`:134,140,213`在tick读target并发布命令，`:273`保留单线程executor。
包装`_on_target`记录接收对象token；命令publish观测其原`_step`调用帧中的实际局部`target`引用与输出对象，避免把tick入口前后的“最新状态”猜成实际输入。
Adapter依据：`adapter_node.py:248,297,298`订阅TrackingCommand并保存同一接收对象；包装回调入口得`t1`，不把`:449,477`的新setpoint时间当终点。
进程内关联可用对象引用、调用上下文与真实返回值实现；所有回调在绑定前装饰，worker闭包/方法引用也须在构造前处理，不能事后替换一个未被使用的名字。

3. **跨DDS边的候选能力门：先做最小native probe，不先扩展RMW绑定**
最小受控PoseStamped native03已实际运行：单writer 8/8为OBSERVED_CANDIDATE，竞争writer 16/16为UNKNOWN；仅证明该次能力，尚不承诺原算法完整链。[归档与独审](../tools/diagnostics/humble54_timing_capability_probe01/native03/)，summary SHA256 `e6bbeeaa85d745cc9254b4ca30860a1541ddfafb8526fc47df6316554bd896bd`。
原安装副本`rclpy/executors.py:398–407`先取得`(msg, info)`，再丢弃info并调用单参回调；固定tag rclpy3.3.22的`subscription.cpp:135–138`只给source/received_timestamp，未给publisher_gid/sequence；不能假设现成双参MessageInfo可用。
native03在固定版本原`_take_subscription`返回时临时用当前线程Python profiler读取实际`msg_info`，保留原take恰一次、原返回对象、异常和执行顺序；对完整10个typed字段逐位核对，CDR未定义padding不作字段。原executor未改，profiler开销及原算法透明性仍未量化。
精确Debian FastDDS2.6.12原源码`DataWriterImpl.cpp:532,842`同步write/add，`DataWriterHistory.cpp:245`调用`WriterHistory.cpp:89`生成sourceTimestamp，`Time_t.cpp:48`用system_clock；已登记生命周期补丁未改这些writer文件，仍须核实际加载库与native行为。
固定tag rmw_fastrtps6.2.10的`rmw_publish.cpp:61`同步write，`rmw_take.cpp:53–66`取sample的source_timestamp、gid及sequence；以上静态线索不能替代实际安装API/时钟域/采样点验证。
每次原publisher.publish前后以成对realtime/monotonic读数夹住调用，记录成功/异常和原发布对象token；同一writer的窗口连同测量/时间编码不确定度必须不重叠，时间锚点须一致且无倒退。
仅当接收DDS source_timestamp非零、未复用、落在唯一完整成功publish窗口内、整条消息与原发布消息一致、writer归属及所有发布均受控可验证时，才联结其实际take对象；source_timestamp不是ROS header时间。
窗口重叠/时间戳重复或窗口外、realtime跳变、来源域未知、图谱竞争writer、漏记、异常或整消息不一致均为UNKNOWN；禁止最近窗口/同header/payload单独匹配。native03图谱轮询最大间隔约10.7ms，仍不能证明采样间绝无短暂外部writer，故只称候选。
覆盖Detector→Estimator、Estimator→Controller、Controller→Adapter三条边，并验证重复payload/相同header仍可区分；若最小probe不满足门槛，先交局部分段，完整bench E2E保持NOT_OBSERVED，再单独评估旁路sample身份hook。
有了该能力，完整链为`RGB/Depth对象→实际Snapshot→worker→实际frame sample→接受update→TargetState sample→Controller所用对象→命令sample→Adapter回调`。
TargetState预测可产生多个command/tick：每个实际command独立登记，另按原接收机会报告首个有效命令及后续信息龄；两者不能混成一个无定义样本。
总账保留每个回放输入机会、实际接收/提交/接受/发布/接收/消费计数；缺边、重复、未接受、覆盖、过期、掉日志、异常和未产生有效命令均有原因，unknown不填0。
统计只给已知子集median/p95/max和覆盖率、吞吐、丢帧/unknown计数；不把已知子集当整段性能，也不以此把旧strict结果升级。

4. **最小验证顺序与交付**
先完成源码/SHA/话题清单和无ROS假对象验证：每个wrapper原调用一次、字节与参数不变、线程/异常行为保留；明确hook边界，不先做全量回放。
原UAVHumble22的最小native03已完成take元数据、窗口时钟域、重复payload/相同header及真实竞争writer验证；无ROS测试覆盖其他UNKNOWN分支。完整bench仍须在所有重任务及真实子进程退出后安排独占窗口，不能把小探针当完整输入/输出透明性验证。
用短开发片段核原frame实际进入worker、拒绝测量不刷新血缘、预测继续旧token、Controller多状态切换时记录真实所用对象；任何缺边停止E2E结论。
能力门通过后才回放固定完整开发输入；记录CPU/线程数、速率、冷/热启动、观察开销及日志丢失，保留所有失败。先少量配对开/关观测确认输入/输出字节透明性，时间扰动如实报告。
需要完整血缘时优先在外部wrapper记录固定长度事件到有界异步缓冲，后写盘；不得在热点路径额外做图像hash、推理或阻塞IO，缓冲溢出使相关样本unknown。
交付新的bench定义、原输入/冻结源/权重/observer/RMW版本绑定、实际图谱、逐机会血缘与端点、原始trace、统计及限制；当前完整原算法bench仅设计、未实现或运行，历史strict1857/1857 UNKNOWN和物理E2E NOT_OBSERVED不变。
