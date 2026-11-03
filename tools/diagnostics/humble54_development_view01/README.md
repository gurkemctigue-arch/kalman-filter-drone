# Humble54 开发成果查看页

在项目根目录执行：

```powershell
python tools/diagnostics/humble54_development_view01/build_view.py
```

输出 `results/diagnostics/humble54_development_view01/index.html` 和同目录的
`inputs_receipt.json`。页面是生成时快照，原实时监控页另行链接；生成器不会启动浏览器、监控器或仿真。

固定输入为原 core12、extension16 两个 plan，各槽小型 started/终态 JSON，以及已归档的
独立 safety03 四槽事实。每个 JSON 限制为 2 MiB。两 plan 固定原文件 SHA-256；校验 plan 内容摘要、
终态内容摘要及 ID/plan/name 绑定，只用于输入追溯，不重新判断实验结果。

页面展示原 `status`、`engineering_result`、`execution_status`、开始/结束 UTC、终态 SHA-256，
以及 `engineering_evidence.measured` 中的 base_link 距离/高度 RMSE。缺失指标保留为空；
已启动但无终态仅表示登记状态，不表示当前进程仍存活。录像、首/中/末帧和小报告仅链接原发布目录，
不读取或自动加载媒体内容。

开发 28 槽、独立安全 4 槽与正式 280 槽分别显示。正式 0/280 是准备时项目负责人给出的当前登记边界，
本工具不扫描正式矩阵，后续正式启动后应更新此边界或停用这份快照。开发 PASS 不等于项目完成。

不读取 telemetry、bag、模型或压缩归档，不校验整包，不写 frozen。输入凭证记录所读小文件的原字节
SHA-256、大小与修改时间，以及页面 SHA-256。刷新网页不会更新数据，需再次执行生成器。
