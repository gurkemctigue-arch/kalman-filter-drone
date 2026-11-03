# final55 的固定源 staging driver

`stage.py` 实现已审 `planning/reliability-v4-final55-offline-overlay-20261103.md` 的源复制和冷构建前叠加，**不会调用 WSL、ROS、colcon、仿真、bag reader、evaluator、正式 registrar 或 gate**。默认只有只读 preflight；显式 `--execute` 才建立一个新的 staging 和一个新的外部 receipt 目录。它不创建未来 cold root，不执行旧卡后续步骤。

当前 profile01 固定原54 core12和extension16 probe01计划、原完整map、固定10份文件及外部模块/合同的实际SHA。它不自动寻找替代计划、选择成功槽、修改pins或接续失败试验。原28槽只要有未闭合、缺terminal、INTERRUPTED、基础设施停止、非整数0退出或残留，就拒绝。

2026-11-03 root已决定：原extension probe01第8槽待原生idle后由原normal CLI登记INTERRUPTED，并另建完整extension16 probe02，旧结果全部保留。因此本profile01不能被当作后续实际stage资格；这里只交付固定规则实现和合成验证。待probe02计划及其合同实际生成后，另审并建立具名profile02，不能在本profile01注入任意动态pins，也不提前改本版pins。

## 运行条件

- 在真正的 `UAVHumble22` Linux 中直接运行；不会从Windows自动启动WSL。
- 原28槽和owner/子进程均已闭合；现有机器SITL锁可独占读取，`/proc`没有PX4/Gazebo等重任务。读取模型/完整源哈希只发生在这些前提通过之后。
- 原54源根及其results符号链接、具名小元数据和完整1585项源map精确匹配；原六模型/五runtime的值仍包含在完整308字典里。
- 当前overlay根只读取10个具名小文件，其他workspace内容不会复制。新module和其test在stage内仅为合成测试依赖。
- 实际生产 `--sensor-module` 和 `--sensor-contract` 已存在，位于新旧冻结树和原results证据目录之外。推荐先复制到一个独立具名工具目录并核SHA，再传其路径；descriptor保存实际canonical绝对路径。不会在这里伪造完整四槽补证。
- stage、未来cold根和receipt目录都必须尚不存在，父目录已存在且与输入根分离。生产stage位于`/root`，未来cold根符合原公开freeze的专用`/root/uav_tracking_fullplan_NAME`命名。

空闲guard会阻挡原runner识别的Harmonic `gz-sim-*`、ROS节点/录包及具名collector、owner和评价/提取任务，但进程筛选与SITL锁**不能独立证明Windows owner终态闭合**。未来profile02实际启用前，仍须另审并绑定具名owner正常退出/闭合收据，不能把槽间暂时无flight误认为监督器已结束。本profile01因已决定的原INTERRUPTED路径不具备实际stage资格。

## 未来调用示例

以下只展示调用格式，没有在本轮执行。按当时实际情况选择全新路径；失败目录保留，不能覆盖复用。

```bash
tracking_project='/mnt/d/基于yolo和卡尔曼滤波'
tracking_driver="$tracking_project/tools/staging/final55_offline_overlay_20261103/stage.py"
tracking_python=/root/uav_humble22/venv/bin/python

# 默认只读：不会创建stage或receipt目录。
"$tracking_python" -B "$tracking_driver" \
  --source-root /root/uav_tracking_fullplan_v4_humble54 \
  --overlay-root "$tracking_project" \
  --stage-root /root/uav_tracking_final55_staging01 \
  --final-root /root/uav_tracking_fullplan_v4_final55 \
  --receipt-directory /mnt/d/WSL/UAVHumble22-validation/final55_staging_driver01 \
  --sensor-module /mnt/d/WSL/UAVHumble22-validation/final55_input_evidence_tools01/evidence.py \
  --sensor-contract /mnt/d/WSL/UAVHumble22-validation/final55_input_evidence_tools01/contract_canonical02.json
```

对将来另行审定且满足全部条件的固定profile，核对真实preflight输出后才使用相同参数追加 `--execute`；当前profile01按上文决定应拒绝，不能用于实际stage。preflight没有输出文件，可由调用方将stdout保存到新的外部日志；不要在命令中让日志文件覆盖任何输入。正式执行会再次完整preflight，而不是信任先前的PASS字符串。

## 实际执行内容

1. 严格核原两个plan文件SHA/内容摘要、完整矩阵/seed、全部28个原终态和flight命令/退出/UTC；保留原FAIL或INCOMPLETE，它们不因此变成工程PASS。
2. 核原完整1585项文件map及其results链接，核308源map、六模型子集和185 scanner名集及每个SHA。通过认证的原map逐文件复制，不遍历复制当前workspace。
3. 只从新stage中排除原批准的两个nested build目录里的精确17项，普通results目录保存原真实research report。禁止扩大公共过滤规则。
4. 先验证复制基线完整map，再覆盖固定8份原文件、增加2份原本不存在的module/test依赖，并在主协议的cold前DRAFT字节加入descriptor；其余科学字段和数值门保持。
5. 核更新后的完整map、308/185/277字典的精确名集和值；旧/新classifier规则完全相同。完整cold源预期1570项仅为导出结果，完整路径和字节比较才是依据。
6. 再核54完整源、原小输入和28个终态没有在复制期间变化，保存外部started/outcome及完整各层map。失败时保留stage和FAIL receipt，不自动清理或重试。

成功状态为 `PASS_STAGING_ONLY_NOT_COLD_OR_ADMISSION`。然后仍须由root在单一原生窗口从stage自身运行公开cold wrapper，并完成真实验证；本driver不会替代这一步。cold后不能补代码/工具/descriptor，仅允许原卡的三个planning规范文件按规定改变。

## 合成测试与平台边界

```powershell
python -B -m unittest discover -s tools/staging/final55_offline_overlay_20261103 -p test_stage.py -v
```

测试只使用临时tiny JSON、源码和明确标注的占位字节文件，名为`.pt`的测试文件不是模型；不读取项目真实权重或bag。Windows当前没有建立目录符号链接的权限，因此便携测试仅替换严格的`source_snapshot` OS链接边界，其他复制、完整map、固定pins、descriptor和失败保留逻辑实际执行；另有测试确认生产边界拒绝普通results目录。生产代码没有该替身、降级参数或Windows运行开关。

在可建立真实目录符号链接的Linux上，同一fixture会自然使用真实链接，不替换该边界。当前Windows合成结果不能宣称Linux symlink/idle guard联调、真实54 preflight、实际stage或cold已通过。最初因无symlink权限全跳过的测试轮不作为通过证据。
