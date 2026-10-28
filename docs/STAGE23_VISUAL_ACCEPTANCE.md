# 阶段二、三结果可视化

`plot_stage23_acceptance.py` 从现有 JSON 报告生成独立 PNG/PDF，不解压 rosbag、不运行 YOLO、不启动 ROS 或仿真。图片使用可移植字体，适用于论文导出；配套数据和文件哈希用于追溯。

```bash
python scripts/plot_stage23_acceptance.py \
  --manifest results/stage23_engineering_v1_matrix/manifest.json \
  --physical-json results/TRIAL_A/physical_identity.json results/TRIAL_B/physical_identity.json \
  --output results/stage23_visual_report
```

也可用 `--statistics PATH/statistics.json` 读取已生成的配对统计，代替 `--manifest`。项目迁移后用 `--project-root` 定位已被清单引用的报告。不提供配对数据时仍输出明确的 PENDING 图，不捏造最终结果。

`paired_seed_rmse` 按行人/汽车和预注册 seed 展示 midpoint、active 的画面中心与独立地平线 RMSE。只有协议兼容的两次真实测量之间才连线。失败或完整飞行证据未通过的测量用红叉覆盖，协议不一致用空心菱形标注；缺失值显示在数值轴之外的状态栏，绝不画成零误差。

`physical_identity_opportunities` 对所有显式传入的试验保留正确、错误物理个体、未知和无新鲜选定检测四类，分母为所有明确任务机会，包括遮挡/未知/未检测时段。任务外的预启动图像不混入身份保持分母。不能用只在已知匹配帧上的正确比例替代这张全体图。早期缺 GT 等 `INCOMPLETE_EVIDENCE` 报告保留为斜线占位行，不计算百分比。

`planned_outcome_ledger` 保留全部预注册项目的 PASS、FAIL、INTERRUPTED、PENDING 和运行状态。它按计划 seed 排列，明确不是杜撰的按时间飞行轨迹。图中的未运行项目、失败数据和早期物理身份不完整报告均不会隐藏。

输出还包括 `plot_data.json` 与 `paired_seed_points.csv`：保存数值、全体分母、状态、失败记录、协议问题、输入及原报告哈希、Python/Matplotlib/NumPy 版本。图是现有记录的展示；单组工程演示和待运行矩阵不能据此宣称十次重复研究已经完成。
