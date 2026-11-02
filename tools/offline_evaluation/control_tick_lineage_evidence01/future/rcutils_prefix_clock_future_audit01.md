# rcutils日志前缀时间：未来最小核验卡

仅准备，当前未运行native probe、readelf或objdump；未验证system-wall结论。须等core12结束并由root安排独占空闲窗口。脚本只初始化rcutils logger，创建进程内ROSClock/TimeSource；无rclpy.init、Node、DDS、Gazebo、PX4、模型、bag或系统时钟改动。

已静态读取实际UNC安装小源码/头/包元数据：

- `/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/impl/rcutils_logger.py:318`调用C入口`rclpy_logging_rcutils_log`，没有时间戳参数；文件SHA `fca546e382884c4025fcf296311c4619f5a58517a8f127508cd9b740a4949ed4`。
- `impl/implementation_singleton.py:32`加载`._rclpy_pybind11`；SHA `10885981244c3e7ade0cc514b198b6f8ee26104570a7685a77163f6ab0638241`。
- 已安装头声明timestamp输出处理器、`{time}`和`{time_as_nanoseconds}`、system/steady API；它们不能证明实际C调用点。没有找到对应已安装C/C++源。
- 包记录为rclpy `3.3.22-1jammy.20260907.213431`、rcl `5.3.13-1jammy.20260907.211637`、rcutils `5.1.10-1jammy.20260907.192648`。这是包记录，尚非本次实际ELF字节或mapped library核验。
- Python throttle限频默认Clock路径与其文档有差异；它不属于prefix时间来源证据。

未来实际执行现有外置脚本：

```bash
bash "$tracking_final/scripts/run_research_session.sh" \
  /mnt/d/WSL/UAVHumble22-validation/rcutils_prefix_clock_probe01.py \
  > "$tracking_fresh_audit_jsonl" 2> "$tracking_fresh_audit_console"
```

`tracking_final`使用届时实际冻结根，两个输出为root事先指定的新外部小文件。先保存脚本SHA和命令/真实退出码；不得覆盖旧证据或重标Windows测试为native。该脚本只在未来Linux窗口导入rclpy，使用实际解释器/模块来源；读取自身`/proc/self/maps`，对logger相关映射核当前path的device/inode并保存小库与Python源的真实SHA，前后重核。

脚本使用同一RcutilsLogger.info，四次设置独立进程内ROSClock为7→9→3→3秒；每次采`time.time_ns()`/`time.monotonic_ns()`前后bracket。stderr显式格式同时输出`{time}`和`{time_as_nanoseconds}`；stdout给对应event_id。此格式属于本次audit，不冒充历史生产格式。独立ROSClock是对照，不是运行真实detector的use_sim_time节点。

随后对probe实际映射的物理库执行只读ELF检查；下列变量必须来自probe映射/实际module path，不凭安装包名假定：

```bash
sha256sum "$tracking_actual_rclpy_so" "$tracking_actual_rcl_so" "$tracking_actual_rcutils_so" > "$tracking_elf_pin_output"
readelf --wide --dynamic "$tracking_actual_rclpy_so" > "$tracking_rclpy_dynamic_output"
readelf --wide --dyn-syms "$tracking_actual_rcutils_so" > "$tracking_rcutils_symbols_output"
objdump -drwC --disassemble=rcutils_log "$tracking_actual_rcutils_so" > "$tracking_rcutils_log_disassembly"
objdump -drwC --disassemble=rcutils_system_time_now "$tracking_actual_rcutils_so" > "$tracking_rcutils_system_disassembly"
objdump -drwC --disassemble=rcutils_logging_console_output_handler "$tracking_actual_rcutils_so" > "$tracking_rcutils_console_disassembly"
objdump -drwC --disassemble=rcutils_logging_format_message "$tracking_actual_rcutils_so" > "$tracking_rcutils_format_disassembly"
```

保留实际文件，即使符号缺失也保留空/拒绝证据。检查`rcutils_log`真实调用的时间函数、传给输出handler的timestamp以及console格式对同一timestamp的使用；若看不到调用链，不用函数名或头文档补结论。系统时间API若落到clock_gettime，还须确认实际clockid参数，而不是看见clock_gettime就断言REALTIME。无需下载源码、安装包或运行ldd。

未来判断只针对本次audit：各event的prefix整数ns是否落在对应system bracket，是否明显不同于steady与受控ROSClock；system/steady前后是否回退；`{time}`和整数ns格式是否一致；源码/库pins前后是否一致；映射path与inode是否一致；是否有LD_PRELOAD或其他无法解释的来源。若不满足，记录unknown/拒绝，不能造PASS。

即使当前安装验证成立，也不追认所有历史process曾加载相同库、格式或环境。现有历史日志没有逐process运行库证据时保留此边界。

如未来获准分析已有`INFERENCE_JOB_TIMING`前缀，最多增加辅助“完成job日志事件的system-wall间隔率”。对完整同一试验/进程、严格解析且唯一job_key、N≥2的完成事件，可报告`(N−1)/(最后时间−首时间)`与覆盖数、unknown/重复/异常原因。它只描述已记录事件间隔；不含首事件之前和末事件之后的区间，不能跨试验拼接。缺失prefix、重复job_key、非有限数、时间回退等必须保留，不任意nearest修复。

不能将1/平均productionprefix耗时代替吞吐；prefix不等于perf_counter绝对worker结束点；不能据此声明精确在线FPS、控制吞吐、因果E2E或历史全部process的system-wall率。该audit也不修改冻结54、协议、算法或正式实验分母。
