# 离线检测评价的配置与缓存来源

`scripts/evaluate_detection_recordings.py`评价已提取RGB图像上的低置信度离线YOLO输出。它不运行仿真、不读取bag、不更改在线检测器。Precision、Recall和mAP只描述独立可见标签审核后的仿真子集；几何排除、缺图及漏检机会继续保留，不能改称整份正式研究的总体检测精度。

## 配置来源

默认 `--settings-source historical` 显式保留原语义：person用YOLO11n/320/2线程，car用YOLO11s/480/2线程，CPU、confidence floor0.001、NMS IoU0.7。报告会写出这组实际参数；默认不会因v4在线汽车使用640/4线程而自行变更。

新版录制应使用：

```bash
python scripts/evaluate_detection_recordings.py /path/to/extraction/recording.json \
  --output /path/to/new_detection_evaluation --settings-source recorded
```

recorded模式从 `recording.json` 的 `source_trial` 读取原槽的 `run_config.json`、`configuration/runtime_parameters.yaml` 和 `configuration/source_sha256.json`。有效YAML中的类别、分辨率、线程必须与非空run override一致，实际权重文件SHA必须匹配原飞行登记。当前v4应解析为person320/2和car640/4；脚本按保存值核验，不靠版本名称猜测。

权重移到新位置时可用 `--car-model-path /new/path/yolo11s.pt` 或person对应项；recorded模式仍要求字节SHA相同。分辨率/线程CLI若与recorded值冲突则拒绝。缺配置、缺原模型hash、缺实际文件或CPU以外设备均拒绝，不触发YOLO自动下载。异机旧Linux绝对路径需要在可访问原配置的环境执行，或先按明确来源迁移工件；`explicit`不等于原飞行配置已经核验。

若有意做另一组离线推理，可逐类别声明完整参数：

```bash
python scripts/evaluate_detection_recordings.py person_recording.json car_recording.json \
  --output /path/to/new_explicit_evaluation --settings-source explicit \
  --person-model-path models/yolo11n.pt --person-image-size 320 --person-threads 2 \
  --car-model-path models/yolo11s.pt --car-image-size 640 --car-threads 4 \
  --confidence-floor 0.001 --iou-nms 0.7
```

每个输入类别都须提供model/size/threads。该结果标为explicit离线实验，不冒充原飞行的实际检测精度。低confidence用于AP曲线，原在线confidence threshold另存，二者不能混称同一阈值。离线wall推理耗时也不能替代飞行FPS或端到端控制延迟。

## 缓存与审核

新 `low_confidence_predictions.json` 为schema2，包含 `provenance` 和 `predictions`。provenance绑定：

- 实际权重SHA、类别/COCO ID、imgsz、threads、conf、IoU、device及配置来源；
- recorded模式三份原配置/登记的实际文件SHA；
- 当前评价器与metric helper的源码SHA；
- `recording.json`的完整SHA及每个图像机会的文件名、实际图像SHA/大小或明确缺失状态。

复用须显式传 `--reuse-predictions`，并通过全部绑定及行集合核验。所有存在图像都须有预测条目；漏检保存空列表，缺图不能编造预测。旧裸时间戳cache、任何模型/参数/源码/图像变化、缺行或外来行均拒绝。复用不导入YOLO、不运行推理，也不重写原cache。新推理发现已有cache会拒绝，请保留旧目录并用新的输出目录。

视觉审核也须绑定当时的图像/配置。首次运行仍生成候选指标、图像与contact sheet，`reviewed_metrics=null`。检查真实图像后，在review文件中写：

```json
{
  "approved_frames": {"trial_name": ["18.000000", "19.000000"]},
  "cache_provenance_sha256": {"trial_name": "copy_the_actual_digest_from_that_trial_detection_report"}
}
```

摘要来自该trial `detection_report.json` 的 `cache_provenance_sha256`，不是示例字符串或cache文件SHA。审核只批准确认可见标签有效的帧；不能自动批准整张contact sheet、复制旧时间戳或只挑检测成功帧。随后使用相同命令加 `--reuse-predictions --review-file reviewed.json`。缺少/不匹配的审核摘要保留 `PENDING_INPUT_BINDING`，不会把旧时间戳批准套用到新图像。最终汇总仍绑定review文件SHA。

此修复只核验离线来源。真实新版录制抽样、低置信度推理、可见标签复核和正式统计尚须执行；schema2 cache通过不等于工程飞行PASS。历史v3结果和裸cache原件不改写。

轻量验证：`python -B -m unittest discover -s tests -p test_detection_recording_provenance.py -v`。夹具覆盖配置冲突、同hash模型重定位、所有cache绑定、缺图/漏检、旧cache、错行、审核绑定及mock推理实际收到640/4参数；不加载真实YOLO或bag。
