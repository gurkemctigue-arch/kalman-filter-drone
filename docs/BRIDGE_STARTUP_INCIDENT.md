# ROS–Gazebo bridge 启动崩溃调查记录

## 已确认的现象

一次阶段二试运行中，`ros_gz_bridge/parameter_bridge` 在初始化 RGB 桥接附近以 `-11` 退出。内核保留了对应故障：

```text
[413.920530] traps: parameter_bridg[4344] general protection fault
ip:797ab17c93ae sp:797a9dff97a0 error:0
in libzmq.so.5.2.5[797ab1777000+68000]
```

因此已经确认故障发生在 bridge 进程内的 libzmq。图像桥接的日志位置只能说明时间关系，不能证明具体 ROS 回调是根因。没有可用 core dump，也尚未捕获故障时各线程的调用栈。

当时安装版本：

| 组件 | 版本 |
| --- | --- |
| ros_gz_bridge | `1.0.24-1noble.20260920.234644` |
| gz_transport_vendor | `0.0.9`，提供 gz-transport `13.6.0` |
| rclcpp | `28.1.22` |
| rmw_fastrtps_cpp | `8.4.4` |
| libzmq5 | `4.3.5-1build2` |

已将内核故障地址换算为 ELF 虚拟地址 `0x6b3ae`，并用本机 libzmq 反汇编确认匹配的指令字节。附近指令表现为指针/过滤结构遍历；库没有调试符号，因此这里不声称已经确定 C++ 函数或唯一根因。

## 源码核查

[ros_gz 1.0.24 bridge_handle.cpp](https://github.com/gazebosim/ros_gz/blob/1.0.24/ros_gz_bridge/src/bridge_handle.cpp) 的 `BridgeHandle::Start()` 先启动 publisher，再启动 subscriber。[factory.hpp](https://github.com/gazebosim/ros_gz/blob/1.0.24/ros_gz_bridge/src/factory.hpp) 在建立 Gazebo subscriber 前检查 ROS publisher，并由回调持有其 `shared_ptr`。这不支持“Gazebo 首帧到达时 ROS publisher 尚未创建”的直接解释。

一个仍需验证的并发窗口位于 [gz-transport 13.6.0 NodeShared.cc](https://github.com/gazebosim/gz-transport/blob/gz-transport13_13.6.0/src/NodeShared.cc)：

- `RunReceptionTask()` 第 336–364 行在接收线程执行 `zmq::poll`，这一段未持有 `this->mutex`。
- `OnNewConnection()` 第 1138–1156 行在 discovery 回调持有该 mutex，对同一个 SUB socket 执行 `connect` 和订阅过滤器设置。
- `RecvMsgUpdate()` 本身持有 mutex，但它发生在 poll 之后。

非线程安全的 SUB socket 可能在 poll 和订阅设置期间被并发访问。这与故障库及指令位置相容，但没有故障调用栈或并发检测结果，不能当作已证实根因。

## 当前结论与下一次采证

分别在没有仿真数据及有仿真数据时，用 gdb 观察初始化约 25 秒，均未复现。这个结果只能说明故障不是每次初始化都出现；不能据此宣称已修复。失败试验仍须计入试验记录。

后续真实运行如再次发生，应在同一实际 runner 中捕获 `thread apply all bt full` 及所加载共享库列表，并保留该次配置与退出码。无需为等待偶发故障而反复启动仿真。

可评估的应用层规避是：以暂停状态启动 Gazebo，在 bridge 和订阅者初始化后再恢复仿真，减少高频数据到达时的订阅变化。它目前只是候选规避，不保证解决问题。拆分图像 bridge 进程或使用 lazy bridge 同样只可能隔离/减小暴露窗口。

本次调查没有修改系统 ROS/Gazebo/libzmq 包。若未来实施底层修复，应让接收线程串行处理 SUB socket 的连接、过滤器与接收操作，并对延迟和吞吐重新验证；不应在没有调用栈证据时直接替换全局库。
