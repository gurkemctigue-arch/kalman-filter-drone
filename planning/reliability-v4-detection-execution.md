# v4独立检测审核执行卡

本卡依据当前源码与`--help`只读核查；没有解包bag、运行YOLO、生成图像或批准任何正式帧。选源来自[前瞻交付选择](reliability-v4-delivery-selections.json)，不是新的性能实验协议。检测报告只覆盖经实际审核的全可见仿真子集，不代表280次飞行、遮挡场景或真实环境总体精度。

## 固定选源与实际工作量

| 类别 | 正式核心槽ID | 抽取参数 | 必须核查的图像与分母 |
| --- | --- | --- | --- |
| person | `person_stage1_velocity_seed1000` | `--sample-period-s 1 --max-images 45` | 最多45个抽样机会；查看全部实际存在的源RGB，合格与排除均核查 |
| car | `car_stage1_velocity_seed1000` | 同上 | 同上 |

两份录制最多90个抽样机会。实际图数、合格图数与批准图数现在未知，必须从原`recording.json`及报告填写。每份合格图的contact sheet为每页12图，最多4页；两类最多8页。contact sheet只覆盖存在且几何合格的帧，几何排除图还需查看抽取目录的原始PNG/overlay；缺图没有可看的图，保留缺失原因。审核人员可以是代理，不要求用户亲自点击90次；必须实际看图并留下逐帧判断。

选源不以PASS、检测成功或文件是否齐全为条件。槽失败也提取其实际可用内容；缺录制/无足够合格图保持缺失，不能换seed或借旧Jazzy图补数。这不是两类各十次独立检测实验，帧也不是独立飞行重复。

抽样从**第一条检测诊断机会**开始，按时间排序，每次选择后将下次阈值设为该时刻加1秒，最多45条；不是严格整秒网格，不保证从FOLLOW开始或覆盖FOLLOW末尾。即使在线检测列表为空，也保留该诊断机会。没有诊断消息的相机帧不在此抽样总体，不能把`sampled_opportunities`称为全部RGB帧数。

## 当前入口与兼容性检查

当前真实CLI：

```text
extract_research_recording.py TRIAL --output DIRECTORY --target-class {person,car}
  [--sample-period-s 1.0] [--max-images 45] [--skip-images]

evaluate_detection_recordings.py RECORDING_JSON [RECORDING_JSON ...] --output DIRECTORY
  [--settings-source {historical,recorded,explicit}]
  [--review-file REVIEW_JSON] [--reuse-predictions]
  [--person-model-path PATH] [--person-image-size N] [--person-threads N]
  [--car-model-path PATH] [--car-image-size N] [--car-threads N]
  [--confidence-floor 0.001] [--iou-nms 0.7]
```

`run_research_recordings.py`固定旧`stage1_final_v2`四录制及历史推理默认，不能作为v4入口。`stage2_identity_contact_sheet.py`是另一套身份诊断，不生成本检测审核所需批准合同。

正式后先检查以下真实条件，再开资源窗口：

- 从**实际不可变核心plan**的`trials`按上述槽ID查`directory`，不要把逻辑ID直接猜成文件夹名。记录plan、槽record、bag完整性报告与本选择文件的SHA；保留原终态。此卡不读取或更改原终态。
- 原目录必须有`rosbag/metadata.yaml`及实际存储、`telemetry.jsonl`、`summary.json`、`run_config.json`、`configuration/runtime_parameters.yaml`、`configuration/source_sha256.json`。`recorded`推理要求三份配置/权重登记实际存在。
- 抽取器要求诊断`/tracking/detection_diagnostics`、RGB`/camera/color/image_raw`、CameraInfo、`/ground_truth/poses`与`/ground_truth/vehicle_poses`；独立真值中必须唯一解析到`target_person`/`target_car`与`stage1_uav`。同采集时刻多条`/tracking/observations`会拒绝。
- 抽取器只支持此处的单目标、固定`x500_stage1`相机。它静态展开`models/x500_stage1/model.sdf`，不读取主动云台关节真值，不能直接拿阶段三主动或多目标bag替代。当前stage1世界确实采用该模型，但正式bag仍须实查topic/真值和模型来源，不能仅凭组名认定兼容。
- 必须在能访问原Linux路径且已构建ROS消息的环境执行。`research_env.sh`载入本源码树的ROS/overlay；需要`rosbag2_py`、cv2、NumPy、PyYAML及后续Torch/Ultralytics。静态相机外参还调用`gz sdf -p`，使用`/root/PX4-Autopilot/Tools/simulation/gz/models`展开继承模型；这是SDF解析，不启动仿真。
- 使用与实际飞行一致的最终冻结模型、mesh、外参和camera intrinsics。核当前SDF与槽内`configuration/x500_stage1_model.sdf`、目标模型快照一致；抽取记录展开SDF摘要及mesh源摘要。相机/mesh不一致或关键topic缺失时停止，登记缺项，不用在线检测框替代GT。

当前CLI**不要求额外静态Gazebo录制**：可从上述固定相机飞行bag提取静态网格投影标签；“静态渲染”指目标视觉网格没有骨骼动画，不指飞行器/目标不运动。若原包不满足条件，它也不会自动补拍静态数据。额外录制须作为另行说明的补充，不能顶替预指定缺失槽。

## 抽取与第一次低置信度推理

以下为后续执行模板，变量必须先替换成实际plan解析的路径。当前没有执行。输出都位于原槽之外的新目录，不使用`--skip-images`，不重写历史录制。

```bash
evaluation_root='/absolute/final/frozen/source'
person_trial='/absolute/directory/from/core-plan/person-slot'
car_trial='/absolute/directory/from/core-plan/car-slot'
detection_run='/absolute/new/v4_detection_seed1000_run01'

cd "$evaluation_root"
bash scripts/research_env.sh scripts/extract_research_recording.py "$person_trial" \
  --target-class person --sample-period-s 1 --max-images 45 \
  --output "$detection_run/extracted/person"
bash scripts/research_env.sh scripts/extract_research_recording.py "$car_trial" \
  --target-class car --sample-period-s 1 --max-images 45 \
  --output "$detection_run/extracted/car"

bash scripts/research_env.sh scripts/evaluate_detection_recordings.py \
  "$detection_run/extracted/person/recording.json" \
  "$detection_run/extracted/car/recording.json" \
  --output "$detection_run/proposed" --settings-source recorded \
  --confidence-floor 0.001 --iou-nms 0.7
```

`recorded`从实际YAML/override取值并核原模型SHA；预计person320/2线程、car640/4线程，**最终以保存值为准**。历史默认car480/2不适用于本次。实际模型已迁移时，可加对应`--person-model-path`/`--car-model-path`指向同SHA文件；不会自动下载权重。不得用`explicit`掩盖原配置缺失。

第一次会对**每张存在的抽样源图**推理，包括几何不合格图；低confidence输出用于AP，不是在线0.45工作点。子目录键为`Path(recording.source_trial).name`，未必等于上述逻辑槽ID。输出：

- `proposed/<实际trial basename>/low_confidence_predictions.json`：schema2原始cache；
- 同目录`review_<原抽样index三位>_<时间六位小数>.jpg`、`contact_sheet_00.jpg`等：只含几何合格图，GT为cyan、预测为green；
- 同目录`detection_report.json`及根汇总：第一次`reviewed_metrics=null`，候选指标不作为正式审核结果。

原`frame_*.png`是模型输入；`*_overlay.jpg`和review图只用于审核，不能再作为推理输入。sheet只画confidence≥0.45预测，cache仍保留≥0.001输出；看不到绿色框不能成为拒绝GT的理由。

## GT与批准条件

GT来自目标SDF中的全部视觉mesh（OBJ/DAE）、视觉pose/scale、Gazebo独立目标/机体姿态、有界插值与固定相机外参；不使用PX4位置、KF位置或YOLO框作GT。姿态只在有括号真值且端点距离不超过0.10秒时插值，不外推。

投影是**amodal静态mesh顶点包围框**。所有顶点须在相机前方0.10米之外；框须有至少约1像素边界，完整在图内；请求遮挡窗及前后各1秒排除。保护窗来自请求事件，不是像素可见性证据，实际黑图/残余遮挡仍需目视发现。并不自动执行完整场景遮挡推理。

逐张查看真实源图与GT overlay，核：目标完整可见、类别正确、cyan框覆盖独立可见物体且没有明显外参/时间错位、同类可见GT没有遗漏、无残余挡板/黑图。只有几何合格且实际可见标签成立才批准；预测正确、错误、空预测都按同样标准判断。不能把GT框改成检测框，不能为提高mAP只留预测成功帧。不合格/待定写明时刻和原因，保留原抽样机会，不改原recording排除记录。

## review JSON精确合同与第二次复用

评价器读取的最小合同如下；键必须是**实际trial basename**，时刻是原`time_s`格式化`f"{time_s:.6f}"`的字符串，不能用图上三位小数或视频帧率推算：

```json
{
  "approved_frames": {
    "ACTUAL_PERSON_TRIAL_BASENAME": [],
    "ACTUAL_CAR_TRIAL_BASENAME": []
  },
  "cache_provenance_sha256": {
    "ACTUAL_PERSON_TRIAL_BASENAME": "COPY_ACTUAL_PERSON_CHILD_REPORT_DIGEST",
    "ACTUAL_CAR_TRIAL_BASENAME": "COPY_ACTUAL_CAR_CHILD_REPORT_DIGEST"
  }
}
```

这是模板，空批准列表不代表审核完成。摘要必须复制对应**子报告**的`cache_provenance_sha256`，不是cache文件SHA或示例字符串；它绑定源图、recording、模型、参数和评价源码。批准时刻须唯一且确有源图。仅旧时间戳批准而无匹配摘要会维持`PENDING_INPUT_BINDING`。

实际文件可另加`reviewer`、UTC审核时间、所看图片/页码及SHA、`rejected_or_pending_frames`和说明；评价器不解释这些附加字段，但最终报告绑定整个review文件SHA，因此应保留真实判断。不要自动把所有候选时刻加入批准表。

保留第一次推理结果及耗时报告不变。为审核版创建新目录，逐字节复制两份schema2 cache，保持相同trial basename子目录；随后：

```bash
bash scripts/research_env.sh scripts/evaluate_detection_recordings.py \
  "$detection_run/extracted/person/recording.json" \
  "$detection_run/extracted/car/recording.json" \
  --output "$detection_run/reviewed" --settings-source recorded \
  --confidence-floor 0.001 --iou-nms 0.7 \
  --reuse-predictions --review-file "$detection_run/actual_visual_review.json"
```

执行前必须已把`proposed/<basename>/low_confidence_predictions.json`复制到`reviewed/<basename>/low_confidence_predictions.json`，核两文件SHA相同；该cache复制路径是复用的明确要求，不会从别处猜找。复用不导入YOLO、不重推理、不改cache，但仍解码图片并重新画review图。任何模型/参数/源码/源图变化或缺失预测行都会拒绝；漏检必须是空列表，不能删掉机会。

## 必须填全的实际分母与报告

每类及两类合计分别登记：

1. 槽原结果、原bag完整性及可用性；`recording.observations`的全部诊断机会数与抽样`len(frames)`另列，前者不是相机总帧数。
2. 原抽样`N_sampled`、实际源图存在/缺失、原几何合格与几何排除数量；保留每次原时间和排除原因。
3. 评价报告`sampled_opportunities = geometric_eligible + len(excluded)`；此处`geometric_eligible`只计**存在源图**的合格帧，原几何合格但缺图也进入excluded。每条excluded保留原因，不能把它们从原机会分母删除。
4. `approved_eligible`、合格但未批准数量、每张批准/拒绝/待定记录；`approved_eligible ≤ geometric_eligible ≤ sampled_opportunities ≤ 45`。两类各自无批准GT时，该类指标待完成，不能只报告另一类聚合。
5. 审核子集GT对象数、预测数（含低confidence）、TP/FP/FN、P/R、AP50和AP50:95。P/R工作点confidence0.45、IoU0.50；AP用101 recall点、IoU0.50:0.05:0.95、全部面积、无crowd/maxDet分层，不能称完整COCO官方评估。
6. 源plan/槽/selection、recording、源图、mesh、配置、权重、源码、cache、实际review和报告SHA，以及实际推理环境版本、命令/returncode、初次运行墙钟耗时。

最终文档入口接入`reviewed/detection_report.json`与实际review文件：

```text
--detection-report /absolute/.../reviewed/detection_report.json
--detection-review-file /absolute/.../actual_visual_review.json
--detection-source-root /absolute/matching/evaluation/source
```

报告构建器会从真实cache/GT重算批准数、排除与P/R/AP；只改汇总数字或批准数不能通过。完成两录制审核也只完成声明子集，不使未执行的飞行或其他条件自动通过。

## CPU耗时：现有证据的实际限度

只读检查的历史`results/detection_research/detection_report.json`中四份录制的`inference.wall_latency_median_s`均为null；旧review也没有新cache provenance绑定。不能从这些报告给v4离线推理或人工审核安排一个可信分钟数。

[历史受控CPU比较](../docs/OPENVINO_CPU_COMPARISON.md)有car640/PyTorch、2线程、预加载图、confidence0.25的118.32毫秒中位数/141.26毫秒p95，但本卡是recorded car640/4线程、confidence0.001，且含解包、图像IO、模型冷启动、NMS、画图及审核；person也没有同配置离线基准。这些数值只能说明历史条件，不能乘90推作本次预计总工时。

正式后以首次真实执行日志分别记录：bag抽取墙钟、初次推理墙钟/子报告中位耗时、复用画图墙钟、实际看图数与审核时段。`--reuse-predictions`的推理中位数为null是未执行推理，不是0秒。安排在仿真退出的独立资源窗口；本卡没有编造截止时间。
