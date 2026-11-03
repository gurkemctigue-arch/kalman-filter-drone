# 停止时点报告生成

用户于2026-11-03明确要求停止实验，改为整理整体报告。本目录工具只读取已有小工件和生成文档，不启动仿真、推理、录包、回放或实验评价；不提供实验自动恢复入口。

交付目录：`docs/project-overview-20261103/`。报告为停止时点的状态报告，正式研究保持0/280，不使用“全部验收完成”口径。

`build_report.py`读取已有核心/扩展终态、绑定导航报告和小型诊断回执，输出共同内容模型、Markdown、HTML、4张图和来源SHA。原始`results/`多数不随Git发布，缺少这些原件时不能仅凭克隆仓库重建数据。

`render_report.cjs`用npm `docx`生成Word。`render_word_pdf.py`通过私有Microsoft Word实例导PDF，使用文档Window的Hwnd核验新进程，保留用户已打开的Word；需要pywin32（本轮使用任务临时目录中的312版本）。PDF与原渲染收据已存在时拒绝覆盖，应先将自己生成的旧版本归档。

`verify_report.py`验证来源SHA、逐槽计数、Word正文、实际Word导出的PDF、页数和页面边界，并生成仅用于排版的逐页PNG。依赖Python matplotlib、Pillow、PyMuPDF。它不是飞行验收测试。

`query_native_stop.py`只查询Linux进程元数据。本次已执行，未找到相关实验进程；WSL环境的idle tail不是实验。

报告制作不修改冻结源`/root/uav_tracking_fullplan_v4_humble54`，不删除旧FAIL/UNKNOWN，不把已有回放诊断升级为正式或物理端到端证据。
