# fixed07：兼容真实 Humble IDL 的 boolean 声明

short03 已真实正常退出：四个算法节点与 replay 全部退出 0，清理完成；其结果仍为 NOT_OBSERVED，0 个候选，504 个命令机会全 UNKNOWN。检测/状态/命令三边分别有 76/454/504 个 UNKNOWN。该次真实结果不重分类。

第一次授权的轻量原生探针没有初始化 ROS、创建发布者、打开录包或启动仿真，仅构造真实消息并经过原 CDR 序列化/反序列化。报告 `schema_probe07_native.json` 保存实际 Python 类型、slots、完整 schema、逐字段结果和完整异常栈。三个 root 类型与 slots 均符合原假设；TargetState.target_visible、TrackingCommand.valid 的真实类型声明是 `boolean`，旧 codec 只认识 `bool`，实际抛出 `TypeError: unknown field type: boolean`。默认空 TargetObservationArray 可通过，实际非空帧中的 TargetObservation 又含同类 boolean 声明。

运行源码仅修改 typed_message.py 的三处集合：标量编码、标量表示验证和序列元素类型验证同时接受 `boolean`。原声明字符串保留，值仍严格要求 `type(value) is bool`；整数 0/1 不作转换。全部字段、数组长度、浮点位表示、类型及未知拒绝规则不变。

第二次单独授权的轻量原生验证已退出 0：三类真实消息完整 CDR roundtrip 的字段表示相等；检测数组含一个真实 TargetObservation，depth_valid=True；状态与命令的真实 boolean 也设置为 True。新 validator 接受前后全部字段。

原 c7 校验器本来只接受 PoseStamped。reducer 原有兼容层会在私有 c7 模块中绑定 `valid_pose_stamped_fields = valid_snapshot`；本次没有新增或削弱这个机制，也没有修改 c7 源码。使用真实 CDR 消息字段、合成 DDS 时间窗口的三项 c7 类型匹配用例均通过。它们仅验证类型兼容及比较路径，不是实际 DDS 关联或软件时延观测。真实 short03 的缺失字段证据无法据此补回，physical E2E 和历史 strict UNKNOWN 不变。

`schema_verify07_native.json` 保存修复后原生兼容证据，`schema_verify07_execution.json` 保存真实退出码。第一次探针 WSL 已退出 0；随后 Windows 包装程序打印混合编码 stdout 时发生 GBK 编码错误，完整 JSON 和原始日志已保留，没有把该打印错误当成原生探针失败或重跑同一探针。

Windows 回归重建真实原生报告中的全部 schema/slots/默认与 CDR 后字段，核对编码一致性；同时检查 boolean 序列、嵌套消息及通过三条 c7 边的完整合成链，整数冒充 boolean 时仍 UNKNOWN。fixed06 的完整源清单与原测试记录已归档到 archive_fixed06，收据 SHA 为 `ece1e1bf25b5235782154f2a9793e652b7d86392ad96e0f7159b5a2ec706ed45`。本次未启动新的 native bench，未修改算法、原输出、timeout 或清理门。
