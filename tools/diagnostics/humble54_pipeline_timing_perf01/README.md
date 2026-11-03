# 隔离的离线归约性能候选

本目录保留与 fixed07 分开的候选，不改变正在运行的原 fullperson、原 reducer、c7 probe、fixed07 源清单或历史输出。它不是正式算法修复，也不推进正式验收 0/280。物理 E2E 仍未观测。

原始 reducer SHA-256：`628271811d1454b1521586cbe332d4d3636f24434ce783fb8f437a51edcb1351`。

原 c7 probe SHA-256：`c7d0050cab71ce6a340c7fc5647531e92334029c8dc38b14393d2dc0058ae426`。候选仍直接调用它的原 `assess()`，没有放宽或复制其门控。

## 已定位的工作量

原 reducer 对每条完整 FOLLOW 命令最多进行 7 次 `only_kind()` 全事件扫描和 1 次导航替换扫描；每个收到的 RGB 再扫全部事件与命令结果。规模约为 `8 C N + R (N + C)`，其中 N 是区间内事件数、C 是命令数、R 是收到的 RGB 数。另外 c7 仍对每个 take 扫所有有效 publish 窗口，各边约 `P T`。

root 的有界尾读报告共有约 619,917 个事件，adapter 本地事件总量 3,724；实际命令回调数不大于该值。以此取上界，前述 `8 C N` 约为 184.7 亿次谓词检查。这里使用的是上界，不能据此推导实际剩余分钟数。CPU 累计增长、RSS 稳定说明仍在计算，不能据此认定死锁。

## 最小变更

- 用保存全部重复项的列表索引完成原精确唯一性查询；缺失键与 `None` 保持原匹配规则，非字符串 token 完整退回原 equality 扫描。
- 导航替换检查按进程保存已接受 update/clear 的时间，以二分执行原严格开区间检查；非标准数值回退原谓词。两端等时刻仍排除，`accepted is True` 保持不变。
- RGB 快照与候选命令按 token 分组；每条命令、每个收到的 RGB、UNKNOWN、重复控制 tick 与首候选时延全部保留。
- `event_index` 映射只构建一次。
- 按固定大小原始字节块更新 SHA 并解析 JSONL，保持 `bytes.splitlines()` 的 CR、LF、CRLF、空行与无末尾换行行为。仍先完整解析所有文件，再进入原 probe 与归约流程。

文件读取变更消除完整单文件 bytes 和 splitlines 的峰值；全部解析事件、嵌套 typed 字段、原排序/顶层字典副本和输出明细仍在内存。本候选不承诺特定 RSS 降幅。c7 的平方级窗口查询尚未优化。

## 构建与验证

在 Windows 项目根目录执行：

```powershell
python tools/diagnostics/humble54_pipeline_timing_perf01/build_candidate.py
python tools/diagnostics/humble54_pipeline_timing_perf01/validate_candidate.py
```

构建器只从精确固定的原 reducer 生成相邻 `reducer_candidate.py`，不会覆盖原文件。验证只使用小型 fake-object 合成事件和临时 JSONL；不导入 ROS、不启动 WSL/native、不读取真实 trace、bag、模型或真实 schema 报告。

测试比较完整输出字典，包括三条 DDS 边的 pairs、每项理由及顺序、全部命令/RGB 明细、分位数与 trace_bindings；覆盖重复唯一性、严格边界、其他进程/被拒绝更新、非 FOLLOW、全局错误、缺失/None、非字符串回退、多命令复用同一 RGB、字节块边界和输入 SHA。合成计时只是单次 Windows 小样本，不代表实际 native 性能。

下一道必要验证是：等待原 fullperson 自然闭合，冻结六路原 trace 与原 summary，再由 root 串行安排新命名离线归约，使用完整原 trace 比较全部输出；真实 trace 等价性当前没有验证。不应以小 summary 或合成测试替代这一步，也不应把候选临时替换到仍在运行的进程。
