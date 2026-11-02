# 固定 12 槽视频来源与缺失台账

原 `--trial DIR` 严格模式保留：任一显式目录缺少视频、配置或摘要即拒绝。
新模式从实际 FORMAL core plan 精确读取事前指定的 seed1000、两类六组全部 12 槽，
不扫描目录、不替换缺片或失败种子。应在 plan 中记录的原生路径环境运行。

只生成库存和浏览器缺失页，不运行 FFmpeg，也不读取或哈希视频：

```bash
python3 -B scripts/build_browser_demos.py --core-plan /absolute/formal/core/plan.json \
  --inventory-only --output /absolute/new/video_inventory
```

去掉 `--inventory-only` 可在仿真及其他重任务停止后转换符合来源条件的录制；
`--selection` 可显式指定原 `planning/reliability-v4-delivery-selections.json`。
选源配置必须仍精确包含原 12 槽。输出目录必须全新且位于录制目录之外。

`manifest.json` 与 `index.html` 始终保留 12 行及固定序号。每行分别记录原槽状态、
原工程结果、原 plan/slot/选源 SHA、缺文件或绑定问题、现有配置/摘要字段匹配情况，
以及摘要中不存在而无法逐字段核对的 seed/scenario 等字段。
PENDING、RUNNING、无原终态或身份/文件绑定不一致的来源不转码；证据齐全的原 FAIL
仍可展示其实际失败录制。配置/摘要须匹配原槽 artifact SHA。原 collector 不登记 MP4 SHA，
因此这种来源明确记为“通过 plan 与已绑定配置/摘要映射的当前完整录制；缺历史视频 SHA”，
不宣称原槽已认证其视频内容。若原槽实际提供视频 SHA，则在转换前核对。
转换前计算当前视频 SHA，转换后再次核对源文件未变，并复用原帧数、尺寸、帧率、
完整时长和每帧相对时间检查；不裁剪、补帧或调速。

`VERIFIED` 仅表示播放副本对应其原录制；文件存在、库存生成或转码成功均不表示飞行通过。
库存模式没有视频内容验证，也不证明浏览器播放已经人工检查。

2026-11-03 已在 Windows 实际执行新增库存模块与原浏览器视频模块的纯 fixture 回归：`test_browser_demo*.py` 共 **16 项通过**；同批交付入口及原回归另有 43 项通过，合计 59 项。原始日志和结果 JSON 见[交付测试原件](../tools/diagnostics/humble53_core_stop_snapshot01/README.md)。本轮测试没有执行真实视频转码、ROS/Gazebo/PX4 或飞行，不构成正式 12 槽视频已齐全或项目验收通过的证据。
