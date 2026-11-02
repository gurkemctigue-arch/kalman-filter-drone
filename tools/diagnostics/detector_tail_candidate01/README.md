# CPU 推理尾延迟诊断候选

这组工具只做离线 CPU 推理测量。工具不启动 ROS、Gazebo 或 PX4，不修改模型、时效门限、身份规则、资源登记或历史结果。首次对照完成后，生产检测器已加入下述最小 guard 候选；输出仍不能作为闭环跟随通过证据。

## 有证据的候选机制

生产 `detector_node.py` 在每次 `on_predict_start` 都调用 `torch.set_num_threads(4)`。官方 PyTorch **v2.5.1** 的 [`ParallelOpenMP.cpp`](ParallelOpenMP.v2.5.1.cpp) 显示：在 OpenMP 路径内，即使参数与原值相同，`set_num_threads` 也没有提前返回；在 `AT_MKLDNN_ENABLED` 条件下会调用 `at::native::mkldnn::clear_computation_cache()`。

这给“只在线程数不符合要求时设置”的候选提供了机制依据，**尚不能单凭源码解释 Humble53 的尖峰**。必须另查实际 PyTorch 构建的 OpenMP、MKLDNN 支持，并比较相同像素的独立进程。`get_num_threads()` 自身可能对新线程进行延迟初始化，所以不能用主线程已设置的标志代替后台线程实际核对。原始下载 URL、字节 SHA-256 和取得时间见 [来源收据](upstream_source_receipt.json)，转载源码附带 [PyTorch 许可证](PYTORCH_LICENSE.txt)。

## 条件和方法

每次命令只运行一个条件，必须分别启动全新解释器：

| 参数 | 具体行为 |
| --- | --- |
| `--policy baseline` | 主线程按原生产路径设置线程并载入 YOLO；每个预测回调都再设置线程数。 |
| `--policy guarded` | 初始化同上；每个预测回调先读取当前线程数，仅不相等时设置，随后核对有效值。 |
| `--policy bounded_aux` | guarded 加初始化时显式设置 interop=1、OpenCV=1；这是额外变量，不与 guarded 的效果混称。 |
| `--wait-policy inherited` | 保留原环境，默认条件。 |
| `--wait-policy passive` | 在导入重型依赖前设置 `OMP_WAIT_POLICY=PASSIVE`、`KMP_BLOCKTIME=0`，同时记录继承值；不保证实际 OpenMP 实现采纳这些变量。 |

使用真实生产 `NonQueuingWorker`，模型由主线程加载、预测在唯一后台线程完成。输入 PNG 先全部载入内存；固定同一 `.pt` 权重、FP32 CPU、imgsz=512，以及原预测的置信度、NMS、LetterBox 相关参数。每个条件默认 **3 次预热 + 12 张图 × 3 遍 = 36 次计量**。3 次预热逐条保存，不混入计量分母。默认计量开始间隔为 1.0 墙秒；如果某次超过间隔，下一次直接开始，不追赶排队。这里的节拍用于检查线程休眠后的行为，并不声称等于完整生产调度。

每次记录预测墙时、进程 CPU 时、调用线程 CPU 时、回调耗时和是否调用 setter、Ultralytics 三阶段时间、所有 NMS 后框、实际模型 tensor hook 形状、后端格式、设备和精度、线程数、PSI 及 rusage。PSI 是整个 Linux 系统的数据，不能归因到单个进程；调用线程 CPU 不含所有原生 worker。回调耗时属于 predict 墙时的子区间，不应重复相加。没有观测到实际形状时写 null，不从 imgsz 猜测。

输出使用全新目录，包含源码及生产 worker SHA、模型 SHA、输入 PNG 与像素 SHA、版本和环境、逐次记录及最终统计。中断或异常保留已写的行并输出 `failed.json`，不把未尝试项当作成功。

## 执行

在已存在的父输出目录下，分别以新的 WSL 进程执行，`<权重>` 使用现有 train20_04.pt 绝对路径：

```bash
/root/uav_humble22/venv/bin/python \
  /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/detector_tail_candidate01/benchmark_cpu_policy.py \
  --input-dir /mnt/d/基于yolo和卡尔曼滤波/results/inference_tail_core41_01/inputs \
  --model '<权重>' --output '<全新baseline输出>' --policy baseline

# 下一条必须是独立解释器；输出目录也必须不同。
/root/uav_humble22/venv/bin/python \
  /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/detector_tail_candidate01/benchmark_cpu_policy.py \
  --input-dir /mnt/d/基于yolo和卡尔曼滤波/results/inference_tail_core41_01/inputs \
  --model '<权重>' --output '<全新guarded输出>' --policy guarded
```

`--repeats 6` 或 `12` 可扩展到 72 或 144 次。`--period 0` 是连续推理条件，要保留与 paced 条件的区别。只在需要单独研究时添加 bounded_aux 或 passive 条件。

实际构建信息可在独立小进程取得：

```python
import json
import torch
print(json.dumps({
    'version': torch.__version__,
    'mkldnn_available': torch.backends.mkldnn.is_available(),
    'mkldnn_enabled': torch.backends.mkldnn.enabled,
    'parallel_info': torch.__config__.parallel_info(),
    'build_config': torch.__config__.show(),
}, indent=2))
```

## 本地验证范围

Windows 实际运行 `python -m unittest tests.test_detector_cpu_policy_benchmark -v`，**12 项通过**。测试覆盖原回调重复调用、lazy backend 重置后的纠正、guarded 同值跳过、无效设置拒绝、显式辅助池变量、回调计时、无排队节拍、环境保留及无效参数拒绝。这些测试没有导入 torch、运行 YOLO 或启动 WSL；真实测量由主执行代理另行记录。

## 首次真实小样本对照及生产候选

主执行代理串行运行了 `D:/WSL/UAVHumble22-validation/detector54_policy01/baseline01` 和 `guarded01`。每组均为 3 次单独保存的预热及 36/36 次计量。独立只读逐样本比较发现：输入清单及模型登记相同；36 对 PNG SHA、实际输入 `[1,3,384,512]`、有效预测参数、PT/CPU/FP32、线程设置和所有 NMS 后框均完全相同。计量区间 baseline 调用了 36 次 setter，guarded 为 0。具名原件哈希、分母、比较字段和统计见 [比较收据](policy36_readonly_comparison.json)。

| 条件 | predict 中位 / p99 / 最大，墙秒 |
| --- | --- |
| baseline | 0.2681 / 0.7731 / 0.8871 |
| guarded | 0.2631 / 0.3904 / 0.3982 |

两组没有随机交错；guarded 期间主执行代理另行导入 torch 取得构建信息，约 2.6 秒，无法精确归因到某一条样本。12 张图来自已消费过的工程诊断集，重复不是新增独立检测数据。本次只有小样本尾部观察，不能据此宣称尖峰消除、Humble53 根因已经确认或闭环已修复。冻结基准脚本的 guarded 逻辑与生产候选相同，但未直接调用新增生产 helper。

生产 `detector_node.py` 新增 `enforce_cpu_thread_count`，每次预测回调读取调用线程实际值，仅不符合要求时才设置，之后再次核对；不成功则抛异常进入原有 worker 错误处理。原主线程初始化、后台 worker、权重、输入、全部控制与身份规则保持原值。没有加入 interop、OpenCV 或 wait-policy 的生产变更。

实际 Windows 运行 `python -m unittest tests.test_detector_cpu_thread_guard tests.test_detector_worker tests.test_inference_timing -v`，**39 项通过**：新增 6 项覆盖首次纠正、同数不设置、外部重置、两个真实后台线程的线程局部读数、设置不生效拒绝、异常送达真实 `NonQueuingWorker` 错误回调；其余 33 项为原 worker、时间记录和生命周期回归。下一步仍需真实生产 helper 基准、新来源冷构建与原生测试、针对原汽车位置场景的完整新飞行验证。

## 真实生产 helper 仪器

[`benchmark_production_guard.py`](benchmark_production_guard.py) 使用独立具名仪器补上首轮 mirror 逻辑的证据边界。baseline 直接使用原 `CpuPolicy`；guarded 的子类在每次回调调用生产 `detector_node.enforce_cpu_thread_count`。传入的计数代理原样委托真实 torch 的 get/set，仅记录显式 Python setter 次数，不包含 PyTorch 内部延迟初始化。导入时同时核对模块文件与函数来源文件，拒绝旧安装或其他目录的替代 helper。输入、模型、逐次框、实际 tensor、CPU/wall、PSI、rusage 等测量沿用原接口；仅显式复制原短 `run` 逻辑，不改原仪器文件、模块全局或函数代码对象。

命令将前述脚本名换成 `benchmark_production_guard.py` 即可。默认每条件 **3 次预热 + 12 张图 × 12 遍 = 144 次计量**，`--period 1.0`，每条件必须独立新解释器和新输出目录。`production_guard_instrument.json` 记录原仪器 SHA、当前 wrapper SHA、真实生产文件路径及 SHA、工厂方式与计数范围；结束前复核生产文件和原仪器未改变。真实基准结果须由执行者另行记录，仪器就绪不等于测量完成。

Windows 实际运行 `python -m unittest tests.test_production_guard_benchmark -v`，**新增 5 项通过**：验证每次实际调用生产 helper、原 baseline 类与 setter 行为保持、错误来源拒绝、真实 helper 异常传出，以及默认 144 次与文件哈希绑定。
