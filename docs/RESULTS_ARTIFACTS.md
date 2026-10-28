# 研究结果工件说明

仓库中的 `results/` 是运行时和研究归档目录，按 `.gitignore` 约定不随公开源码提交。README 和其他文档中提到的报告、日志、视频、rosbag 与验收页面，只有在本地已有对应归档时才可打开；公开克隆本身不包含这些文件，也不会因为打开 Markdown 而自动生成。

本机最终归档的统一入口为 `results/frozen_fullplan_v3/交付入口.html`，可打开视频演示、PDF/Word 报告、计划书和逐次验收。三个阶段的最终执行状态见 [交付状态](DELIVERY_STATUS.md)。

项目的核心代码、配置、测试和可复现命令仍在仓库中。先安装测试依赖并运行单元测试：

```powershell
python -m pip install -e ".[test]"
python -m unittest discover -s tests -v
```

需要生成便携估计器基线时，从项目根执行：

```powershell
python scripts/run_synthetic_experiments.py --target-class both --seeds 10
```

需要查看本地研究归档的静态验收页时，确保 `results/` 已由受信任的归档或研究运行提供，再执行：

```powershell
python scripts/build_acceptance_dashboard.py --results-dir results --output results/验收总览.html
```

该页面只索引已有文件，不启动仿真或补造缺失结果。没有归档时，请以 `docs/` 中的协议、验收边界和测试命令为准；缺少结果工件不能解释为试验通过。
