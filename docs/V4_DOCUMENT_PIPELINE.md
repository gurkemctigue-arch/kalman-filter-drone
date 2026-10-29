# v4计划书与研究报告生成流程

新版入口与旧166+16研究独立，旧报告、完成门和文件不改。当前仅完成代码、合成JSON检查及内存中的Word XML结构检查；未据此生成或宣称真实正式结果。

## 生成来源绑定的文档包

```bash
python scripts/build_reliability_v4_report.py \
  --summary /archive/v4_summary/summary.json \
  --core-plan /frozen/root/results/core/plan.json \
  --extension-plan /frozen/root/results/extensions/plan.json \
  --mode draft \
  --output /archive/new_v4_report_package
```

开发子矩阵也可用，但输出始终标明`DEVELOPMENT_ONLY`。未完成槽和缺失指标保留；无扩展时省略其选项。输出为`plan.md`、`report.md`、对应HTML、`documents.json`和`sources.json`，目录必须全新。计划内容来自[FINAL_PLAN_V4.md](FINAL_PLAN_V4.md)，旧`FINAL_PLAN.md`仍保留历史设计。

最终模式改用`--mode final`，并同时提供：

```bash
  --replay-summary /archive/registered_replay/summary.json \
  --replay-input-manifest /archive/registered_replay_inputs.json \
  --replay-configuration /archive/registered_replay/registered_configuration.json \
  --replay-source-root /frozen/evaluation/root \
  --figures-manifest /archive/v4_figures/manifest.json
```

`--replay-source-root`指定登记的实际评价源码副本，默认当前项目。四法三个输入须成套提供，不能只给一份汇总或PASS布尔值。图表manifest由新版绘图入口产生，绑定准确summary SHA、可选四法summary SHA及每幅PNG/PDF/SVG/CSV的path、bytes、SHA、caption、scope和source_role；Word嵌入PNG，其他格式保留来源索引。图表暂缺则报告pending，不编造图表。

## 来源检查与最终模式含义

工程summary由原计划、槽、评价JSON重新构建并比较，包括原report及终态artifact hash、分组、配对和bootstrap；只修改summary中的均值、通过数或模式不能通过。四法先验证REGISTERED配置和实现/真实核心计划绑定，再核全部20槽的原报告或明确缺失终态。已有数组JSON、export/online/native/truth sidecar与纯数组计算会重新核对，保存的报告数值和汇总也须一致；不读取bag、不运行YOLO或仿真。它不是只读几个状态字符串，因此正式文档构建应安排在独立资源窗口。

FINAL必须满足真实FORMAL核心120与EXTENSION_FORMAL扩展160的不可变计划及全部终态；四法20槽全部有已保存计算报告或运行器记录的明确缺失/无效终态，且登记绑定本次核心原计划。PENDING/RUNNING、开发PROBE、缺少扩展、未登记四法或无来源的20个名字均拒绝。最终统计参数固定10,000次bootstrap和seed20261029。

FINAL不要求所有压力算法PASS，也不以缺失误差补零。工程失败、基础设施失败、EVALUATION_PENDING、右删失、缺失配对和不足十对仍完整披露。完成执行台账不等于工程全部通过，四法20槽均记账不等于20条均有充分证据或完成十次有效配对，更不等于整个项目已经验收。

文件发布前再次检查全部来源未变。保存的`documents.json`含规范摘要与原构建请求；`sources.json`列输入大小/hash/缺失及MD/HTML/JSON输出hash。重新封一个自造摘要也不能绕过原始来源重建。

## 恢复、删失与控制指标的口径

summary与正文现保留`recovery_evidence`：短请求窗的原窗数、测量恢复数、同track/UUID数、变更数、身份unknown、未观察/无时间及条件分母分别计数；显式选框的已确认、原报告右删失、缺失/不一致也分别计数。缺来源的计数为null，实际保存空列表才为0。组计数是窗口池化，误差或时间均值仍以整次飞行为单位。

短窗全部分母上的测量恢复观察比例和同track/UUID观察下界不表示失败率；恢复时间缺失/非法时不强行生成全窗比例。条件恢复率只用已观察且身份检查为布尔值的恢复；时间只用实际同track/UUID恢复。未观察不等于完整观察后失败，当前surface来源也不足以证明整个恢复期限有连续观察。同track/UUID属于操作层连续，不能称独立物理重捕获或ReID；正文另列物理保持下界、wrong及unknown。

显式选框包括初始选择和重新选择，不区分长丢失重捕获。确认比例为已确认除以已确认加显式右删失窗口，缺失/不一致不混入已知分母；右删失不称失败，条件确认时间也不补零。每个飞行保留逐窗证据，CSV同时保留证据JSON。

物理距离/高度的95%绝对误差分位数从原`p95_absolute`读取；有符号误差的`p95`不能替代。位置命令变化率与二阶差分只取间隔不超过0.2秒且连续有效mode2命令，包含有意跟随及重选瞬态，不等于机体实测速度/加速度或纯噪声。各标量保留原样本数，不能以飞行数替代。

## 独立检测审核子集

可同时增加`--detection-report /evaluation/detection_report.json`、`--detection-review-file /review/approved.json`；原评价源码位于独立冻结副本时，指定`--detection-source-root /frozen/detection/evaluation`。只提供其中一个输入会拒绝；两者都没有则显示PENDING，不影响负结果执行报告的生成。

入口核对实际review路径与文件SHA、逐录制子报告、schema2预测缓存SHA和完整provenance、原recording清单、全部图像机会的SHA/缺失、真实模型SHA、已保存推理参数和评价源码SHA。它从同一缓存与独立GT重算原指标及批准/排除分母，不推理、不解码图片、不读bag。只改均值、批准数量或汇总不能通过；仅有旧时间戳而没有cache_provenance绑定时，审核仍为PENDING且不产生正式指标。

正文报告逐录制的采样/几何合格/审核合格/排除数量、原P/R工作点与AP约定、该批准子集mAP。完整入画、静态渲染、经审核的子集边界始终保留，不能写成280次飞行、所有遮挡或真实世界的总体检测性能。离线推理耗时与在线飞行FPS/延迟分开。

## 生成Word与后续PDF检查

先仅核验，不生成Word：

```bash
node scripts/build_reliability_v4_documents.cjs \
  --input /archive/new_v4_report_package/documents.json \
  --python python \
  --validate-only
```

实际资料与图表齐备且资源窗口空闲后，输出新的独立目录：

```bash
node scripts/build_reliability_v4_documents.cjs \
  --input /archive/new_v4_report_package/documents.json \
  --output /archive/new_v4_word \
  --python python \
  --font "Microsoft YaHei"
```

依赖Node与npm `docx`。当前环境已能require该包；在其他机器应先检查依赖。Word生成器调用Python`--verify-package`重建原证据、检查renderer自身SHA，再允许写入；写完再次核验。输出两份DOCX和最后写出的`render_manifest.json`，记录输入/输出SHA、Node和字体。输出目录不得已存在或嵌在原报告包中。

生成与渲染须在能够访问同一批原始路径的环境执行，例如保存冻结证据的Linux环境；仅复制`documents.json`到另一台机器不足以通过原路径和hash检查。最终可分享DOCX/PDF与来源索引，原始证据复核仍使用对应归档环境。

## 当前机器的最小渲染路线

2026-10-29只读探测：UAVHumble22没有Linux Node、LibreOffice、Poppler或pandoc；系统apt候选Node仅12.22.9。Windows已有Node24.15.0、npm docx9.14.0、Word16.0.20527.20088与Python fitz/Pillow；未因探测启动Word。

`prepare_document_node24.py`已把官方Linux x64 Node24.15.0包下载到`/root/.cache/uav_documents/node24-24.15.0/`，31,164,460字节，官方SHASUMS核验SHA256为`472655581fb851559730c48763e0c9d3bc25975c59d518003fc0849d3e4ba0f6`。原`download_manifest.json`保留下载时状态；随后在负责仿真的代理明确释放的空闲窗口完成专属安装，另写`installed_manifest.json`。复现安装命令如下，已有目录会拒绝覆盖：

```bash
python3 scripts/prepare_document_node24.py --install \
  --docx-modules '/mnt/d/基于yolo和卡尔曼滤波/node_modules'
```

安装落专属`/root/uav_document_tools/node-v24.15.0-linux-x64/`，不覆盖系统Node或全局npm。实际可执行版本v24.15.0，SHA256为`d1de76d8edf2fededf6f8b30d244e2c0529ac607923a018283b77e9c74bd932c`；明确给定的现有纯JS docx模块解析成功。Linux专属Node运行21项内存OpenXML断言也已通过，没有落DOCX。之后用该`bin/node`与`NODE_PATH`运行上面的Word生成器，继续保留`/root`原始来源路径；将DOCX输出到`/mnt/d`下新的交付目录，供Windows现成Word排版。

Windows转换入口为`scripts/convert_v4_word_to_pdf.ps1 -InputDocx <新DOCX> -OutputPdf <新PDF>`。它只创建独立COM实例，核Hwnd→PID确为调用前不存在的新进程且文档集合为空后才操作；只打开自身指定的readonly文档，更新字段/目录并导出，再以不保存方式关闭自身文档和已确认归属的实例。不连接或结束用户已有Word，不改原DOCX，已有PDF/sidecar拒绝覆盖。`-ValidatePathsOnly`只查路径与冲突，不启动Word。

该转换脚本本轮只做AST与路径夹具，真实COM/目录更新/PDF输出仍须在最终材料窗口实际验证。导出sidecar明确`PDF_GENERATED_PENDING_PER_PAGE_VISUAL_REVIEW`，保留Word版本、专属PID、原DOCX与PDF SHA和页数。随后用现成fitz导出逐页图片并人工/代理逐页查看，无需安装大型LibreOffice或Poppler。

A4中文文档使用真实标题层级、可更新目录、页眉页码、重复表头、表/单元格双宽度与PNG原比例。生成状态为`DOCX_GENERATED_PENDING_PDF_RENDER_AND_PER_PAGE_VISUAL_REVIEW`，不声称已排版验收。最终还须用实际可用Word或LibreOffice更新目录字段、转PDF，登记渲染器版本，逐页查看中文字体、表格跨页、长ID/hash换行、图像、页码和完整尾页。不得在真实数据未完成时用夹具文档代替。

轻量检查：

```bash
python -B -m unittest discover -s tests -p test_reliability_v4_report.py -v
node tests/test_reliability_v4_documents.cjs
python -B -m unittest discover -s tests -p test_document_runtime_preparation.py -v
```

Python测试只用不可变合成JSON；Node测试只在内存打包标注FIXTURE_ONLY的OpenXML，并检查A4、双宽度、表头、分页属性、标题与目录，不写DOCX/PDF。实际可读性与逐页检查仍待真实文档生成。

## Windows本机入口与独立分享

生成交付前，先对实际最终冻结工程的`results`执行`readlink -f`，把`delivery_root`直接设为解析得到的`/mnt/d`物理路径下的全新目录。`summary`、`figures`、`document_package`、`videos`与`word`均使用这个绝对根。不要把`/root/.../results`符号链接拼写作为报告输出路径：图像路径已解析到`/mnt/d`时，词法`relpath`可能跨越两个路径拼写，生成Windows不可用的相对链接。

本机原证据已在D盘，可通过相对路径指向同项目`results`，无需复制大rosbag。交付后必须在Windows实际打开统一入口、报告、视频与summary，并逐链接核对图像、PDF、CSV/JSON和原证据；不能以生成器退出0代替检查。独立分享包只导出Word/PDF、图、视频与小型索引，明确原始录包等本地证据在分享环境中不可用；复制HTML或保留来源绝对路径，不表示接收者能访问原全部证据。
