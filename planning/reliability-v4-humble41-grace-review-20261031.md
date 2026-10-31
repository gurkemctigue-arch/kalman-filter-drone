# Humble41 推理宽限候选独立复核与撤销回执

2026-10-31。复核基线提交：`9596c35c71db5e1711e2ffa2642ec228abaf66a9`。本轮没有启动仿真，没有修改既有冻结根、原始试验或评价报告。

## 复核结论

不准入临时的 `inference_status` / `inference_pending_grace_s` 候选。已按主代理要求仅撤销本轮三个未提交文件中的对应差异，恢复至上述提交；撤销后、写入本回执前 `git status --short` 为空，`git diff --check` 无输出。

该候选存在以下行为问题：

- `_flush()` 在存在任何较新的进行中推理时直接返回，会取消许多正常的定时输出，未保留连续、独立的状态新鲜度和停止控制证据。
- `_process_observations()` 和 `_publish()` 仍调用原有 `_expire_elapsed_target()`。该函数没有所谓宽限分支，迟到测量进入关联前仍会按最后已接受测量不可逆锁存 LOST。因此单独允许接收超过 `max_observation_age_s` 的帧不能修复这次失败。
- 生命周期记录缺少当前采集 epoch、时间和过期校验，进行中记录也没有可靠的容量上限；不能据其延长身份存续。
- 原有测试夹具没有新增参数和发布器，临时补丁状态下 6 个相关文件共 37 项失败。撤销后同一组的 103 项全部通过。

原有 0.75 秒预测期限、长丢失后的重选要求及控制新鲜度判据继续有效。不能通过暂停状态输出、延长预测期限或改变失败统计来宣称本次可靠性问题解决。

## 撤销后的测试

实际命令在本机 WSL `Ubuntu` 中执行，使用工作区当前源码：

```text
PYTHONPATH=tests python3 -m unittest \
  test_supported_birth_confirmation test_car_surface_adapter \
  test_estimator_publication_expiry test_estimator_timing \
  test_inference_timing test_detector_worker
```

结果：`Ran 103 tests in 0.587s`，`OK`，退出码 0。这是定向行为回归，不代替目标 Humble 环境冷构建或实飞仿真。

恢复后的文件 SHA256：

| 文件 | SHA256 |
| --- | --- |
| `ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/detector_node.py` | `cce6b1c3bce2d16e97b116a72687e5cb42c01b1a5c6992ebaf820bbb54047fda` |
| `ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/state_estimator_node.py` | `b5ad7953b4e5e040b37919431e5be36869116e240eeddd427546089686ef40df` |
| `ros2_ws/src/uav_tracking_bringup/config/stage3_tracking_car.yaml` | `f5627471926d8476043dce1b2fddf16df56127e556c935a18102994700aa2953` |

## 已确认的真实失败时序

来源：`results/frozen_fullplan_v4_humble41/reliability_v4_humble41_probe01_car_stage3_multi_active_seed004/` 的原 `telemetry.jsonl`、`ros.log` 及 `stage2_evaluation.json`。

- 最后正常目标测量采集于 29.8 秒，29.964 秒收到并发布 MEASURED；目标 track 为 3。
- 下一帧采集于 29.9 秒，推理开始于仿真 30.0 秒，完成于 30.636 秒。期间没有新的已接受测量。
- 30.564 秒已经发布 LOST，测量年龄为 0.76 秒。短遮挡关闭请求在 30.6 秒才发生，因此目标在本次遮挡前已经丢失。
- 此迟到帧的采集至完成时延为 0.736 秒，超过原 0.60 秒输入年龄限值。按原行为保留丢失是正确的安全结果，根本问题是推理尾延迟。

`INFERENCE_JOB_TIMING` 的 job `[0,29900000000]` 给出：

| 环节 | 墙钟秒 | 调用工作线程 CPU 秒 |
| --- | ---: | ---: |
| 完整生产工作 | 7.908087 | 5.599296 |
| `yolo_predict` | 7.551139 | 5.355386 |
| `decode` | 0.088369 | 0.034817 |
| `depth_navigation_geometry` | 0.258273 | 0.199294 |

YOLO 调用占总墙钟约 95.5%。锁等待和发布不构成主耗时；工作线程 CPU 计时不包括所有原生线程，不能据此断言是纯计算、CPU 调度或内存因素中的哪一种。

## 降低尾延迟的后续实现建议

1. 在独立目录提取失败帧和前后帧，保持 RGB、模型权重、阈值、输入大小和采集清单不变。先通过同帧重复推理判断异常是否可重现，并分别统计冷启动和热运行结果。
2. 把 YOLO 调用拆分为预处理、网络推理和后处理的诊断计时；同时采集进程 CPU、缺页、内存压力和 CPU 限流。先找出 7.55 秒具体耗在哪里，不把原生线程耗时等同于当前工作线程计时。
3. 对 `torch` 的 1、2、4 推理线程做独立配对压测，限制 OpenMP/BLAS 线程，核对 `torch` 实际线程配置。选择依据应包括 p95、p99、最大时延和同输入检测回归，不只比较平均 FPS。
4. 如 `torch` CPU 仍有长尾，可在独立候选中导出并比较 ONNX Runtime CPU 后端。必须保留同权重、相同预处理、框输出约定、阈值和检测机会分母，先核对数值与框的等价性，再允许进入新的闭环验证。
5. 任何后端或资源设置改变都创建新候选和新批次；原核心 12 的失败不被覆盖。新候选仍需全套定向回归、Humble 冷构建和完整 12 场景验证。正式批次不能据本回执直接准入。
