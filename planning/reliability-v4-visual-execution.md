# v4可视交付命令卡

这是实际运行前的静态操作卡，不是成果或验收记录。复用现有工具，不另建框架。源选择见[前瞻交付选择](reliability-v4-delivery-selections.json)；检测审核见[独立检测执行卡](reliability-v4-detection-execution.md)。全部重工作须待仿真/其他评估明确退出并交接资源窗口。

## 1. 在原Linux证据路径生成快照与科学图

先填写真实最终核心/扩展plan、四法结果和新的交付根目录，不能用开发snapshot或旧Jazzy材料冒充正式输入。下列都是待执行模板：

```bash
evaluation_root='/absolute/matching/evaluation/source'
core_plan='/absolute/final/core/plan.json'
extension_plan='/absolute/final/extension/plan.json'
replay_summary='/absolute/registered/replay/summary.json'
delivery_root='/absolute/new/v4_delivery01'

cd "$evaluation_root"
python3 -B scripts/summarize_reliability_v4.py \
  --core-plan "$core_plan" --extension-plan "$extension_plan" \
  --bootstrap-resamples 10000 --bootstrap-seed 20261029 \
  --output "$delivery_root/summary"
python3 -B scripts/build_reliability_v4_figures.py \
  --summary "$delivery_root/summary/summary.json" \
  --replay-summary "$replay_summary" --output "$delivery_root/figures"
```

`summary`、`figures`目录必须全新。四法缺少完整验证时图表保留pending，不能把omitted/pending当已完成图。实际逐图查看PNG与至少一种矢量导出；核全部状态、核心/扩展分开、每图trial n、误差样本数、窗口池化分母、unknown/删失和无裁切。距离/高度是95%**绝对**误差分位数；操作层恢复不是独立物理ReID。记录所看文件的SHA与具体问题，不能只看脚本exit0。

## 2. 固定seed1000的12条视频

两类×六核心组全部预指定，包含失败/缺视频。先由实际plan查每个槽`directory`，结合完整summary记录原终态，形成12行来源清单。每行保留`slot_id`、实际目录、原结果、原onboard文件有无与缺失原因。**不因缺片或失败换seed**；没有视频的槽仍在清单，工具只处理实际具备输入的条目。

完整12条均具备`onboard.mp4`、`run_config.json`、`summary.json`时，模板为：

```bash
python3 -B scripts/build_browser_demos.py \
  --trial "$person_stage1_velocity" --trial "$person_stage1_position" \
  --trial "$person_stage2_crossing" --trial "$person_stage3_midpoint" \
  --trial "$person_stage3_active" --trial "$person_stage3_multi_active" \
  --trial "$car_stage1_velocity" --trial "$car_stage1_position" \
  --trial "$car_stage2_crossing" --trial "$car_stage3_midpoint" \
  --trial "$car_stage3_active" --trial "$car_stage3_multi_active" \
  --acceptance "$delivery_root/summary/index.html" \
  --output "$delivery_root/videos"
```

上述12个变量均为plan解析出的绝对目录，不是槽ID字符串。若有缺片，只传来源清单中具备三个实际文件的条目；缺失清单同时交付，不能让视频页“完成N/N”冒充12/12。全缺则保持待完成。可用`--ffmpeg`、`--ffprobe`显式指定实际可执行文件。

工具生成完整时长H.264/yuv420p副本，不裁剪、不补帧、不调速，核原帧数、尺寸、帧率、时长与每帧相对时间。manifest的VERIFIED只证明转码对应，不证明飞行通过。实际在浏览器播放每条视频，检查可启动/拖动/结尾、可读标注以及实际出现的遮挡、LOST悬停、显式选框；原录制缺失的事件不能靠转码补出。

## 3. 来源绑定的最终计划书/研究报告包

实际120+160终态和四法20槽记账齐全后，填写全部真实输入：

```bash
python3 -B scripts/build_reliability_v4_report.py \
  --summary "$delivery_root/summary/summary.json" \
  --core-plan "$core_plan" --extension-plan "$extension_plan" --mode final \
  --replay-summary "$replay_summary" \
  --replay-input-manifest '/absolute/registered/replay-inputs.json' \
  --replay-configuration '/absolute/registered/replay/registered_configuration.json' \
  --replay-source-root '/absolute/matching/replay/source' \
  --figures-manifest "$delivery_root/figures/manifest.json" \
  --detection-report '/absolute/detection/reviewed/detection_report.json' \
  --detection-review-file '/absolute/detection/actual_visual_review.json' \
  --detection-source-root '/absolute/matching/detection/source' \
  --output "$delivery_root/document_package"
```

`final`表示完整来源台账，包含FAIL、缺证及删失，不能据此宣称所有工程通过。检测未审核可生成带PENDING的负结果报告，但不能称原计划全部检测指标已完成。开发资料只用`--mode draft`，保留DEVELOPMENT_ONLY。

## 4. 在Linux保留原路径生成两份DOCX

本机器已安装专属Node24.15.0，docx模块位于现有Windows项目；下面输出目录须位于可供Windows读取的新`/mnt/d`目录，而且不能在原文档包内部：

```bash
NODE_PATH='/mnt/d/基于yolo和卡尔曼滤波/node_modules' \
  /root/uav_document_tools/node-v24.15.0-linux-x64/bin/node \
  scripts/build_reliability_v4_documents.cjs \
  --input "$delivery_root/document_package/documents.json" \
  --python /usr/bin/python3 --validate-only

NODE_PATH='/mnt/d/基于yolo和卡尔曼滤波/node_modules' \
  /root/uav_document_tools/node-v24.15.0-linux-x64/bin/node \
  scripts/build_reliability_v4_documents.cjs \
  --input "$delivery_root/document_package/documents.json" \
  --python /usr/bin/python3 --font 'Microsoft YaHei' \
  --output '/mnt/d/基于yolo和卡尔曼滤波/deliverables/v4_final01/word'
```

输出`v4_plan_final.docx`、`v4_report_final.docx`与`render_manifest.json`。不能仅复制documents.json到无法访问原Linux来源的Windows后绕过核验。DOCX生成只证明打包，仍标PENDING_PDF_RENDER_AND_PER_PAGE_VISUAL_REVIEW。

## 5. Windows Word真实排版、PDF与逐页检查

PowerShell执行，使用新的PDF名：

```powershell
& .\scripts\convert_v4_word_to_pdf.ps1 `
  -InputDocx 'D:\基于yolo和卡尔曼滤波\deliverables\v4_final01\word\v4_plan_final.docx' `
  -OutputPdf 'D:\基于yolo和卡尔曼滤波\deliverables\v4_final01\word\v4_plan_final.pdf'
& .\scripts\convert_v4_word_to_pdf.ps1 `
  -InputDocx 'D:\基于yolo和卡尔曼滤波\deliverables\v4_final01\word\v4_report_final.docx' `
  -OutputPdf 'D:\基于yolo和卡尔曼滤波\deliverables\v4_final01\word\v4_report_final.pdf'
```

转换器只操作新建且核实归属的隐藏Word实例，打开自身readonly文档、更新目录/字段/分页并导出；不保存原DOCX。核两个`.render.json`的实际Word版本、原DOCX/PDF SHA和页数。现有DOCX目录字段可在Word打开时更新；不能声称原DOCX内已缓存了转换过程中生成的目录页码。实际COM路线仍须验证，不能用AST/内存XML检查代替。

用现成fitz将两份实际PDF的**全部页面**导出到独立的新目录，逐页查看：中文无缺字，目录页码与正文相符，表格重复表头/跨页正常，8列表格和长ID/hash无裁切，图像清晰，页眉页码和尾页完整。对照PDF实际页数与sidecar；记录PDF SHA、每页检查结果、问题与修复版本。看完页数不能用“一张缩略图”代替。发现问题从源重建新输出版本，保留旧件。

## 6. 真实打开入口和归档

实际打开summary、报告HTML、视频HTML及最终交付导航；逐个点图、PDF、视频和来源索引。使用本地HTTP时要核链接位于实际document root内，不能把服务根目录以外的原bag路径伪作可下载URL。大bag可作为明确的本地绝对路径/独立工件索引保留，不直接塞进Git。

最后归档：图表/CSV manifest、固定12行视频源与缺失清单、转码manifest、检测审核及SHA、文档包sources、DOCX/PDF渲染和逐页检查记录、依赖/权重说明、原bag索引，以及对应GitHub源码commit。没有真实检查记录的项继续标pending；旧v3文档与演示保持历史版本标签。
