# 汽车检测权重与复现资料

本文件说明当前 Humble42 开发候选实际使用的汽车检测器。开发验证、正式实验和跨车型泛化是不同结论；当前尚未完成正式 280 槽验证。

## 权重身份与获取

| 项目 | 实际值 |
| --- | --- |
| 运行文件 | `models/yolo11m_car_sim_train20_04.pt` |
| 模型 | YOLO11m，在本项目汽车仿真图像上微调 |
| SHA256 | `bf7a56de4ae1658f8101fc6089247e8b984c2965b58d6b4963b4b5977e9ca00c` |
| 本机文件大小 | 40,620,517 字节 |
| 原始初始化权重 | `yolo11m.pt` |
| 初始化权重 SHA256 | `d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95` |
| 选择规则 | 固定 20 epoch，使用框架原 validation fitness 选出的 `best.pt`；实际为 epoch 17 |

当前机器已经保存运行文件。原训练输出位于 `D:/WSL/UAVHumble22-validation/humble28_car_train02/runs/train20_04/weights/best.pt`。两份文件的预期身份由上面的 SHA256 确定，不凭文件名判断。下载 GitHub 源码时不会自动获得该二进制；此权重目前没有公开下载 URL，交付时应同时提供这份具名工件及其来源索引。

取得实际工件后，将其放到运行源码根的 `models/` 目录，并核对 SHA256。Windows 可使用 `Get-FileHash -Algorithm SHA256 -LiteralPath 'models/yolo11m_car_sim_train20_04.pt'`；Linux 使用 `sha256sum models/yolo11m_car_sim_train20_04.pt`。上游同名系列的预训练权重不能替代这份微调工件。

## 训练数据与参数

训练资料见[第二轮适配记录](../planning/reliability-v4-car-adaptation02-20261030.md)和[原训练来源收据](../config/car_sim_train20_04_training_receipt.json)。数据共 236 张开发图像，144 张训练、92 张监测，保留 COCO 80 类映射，汽车为类别 2；不是新的单类别输出模型。

图像来自旧开发录制、已消费视角和预先固定的 56 个新仿真视角，均围绕同一 Prius 视觉资产；包含双车、部分遮挡及空背景。标签经实际像素检查，数据划分与模型选择均有原始记录。这些资料已用于开发，不能作为独立泛化测试，也不证明其他车型或真实相机效果。

实际固定训练使用 Ultralytics 8.4.188、CPU FP32、4 个计算线程/1 个 interop 线程，20 epoch、训练输入 640、batch 1、workers 0、freeze 23、AdamW、lr0=0.0001、warmup_bias_lr=0、nbs=64、seed=42、AMP 关闭，不接续此前失败候选。完整有效参数保存在本机上述训练目录的 `args.yaml`，原数据清单和训练终态由收据绑定。仅凭本段参数和缺少原数据的 Git 克隆，不能逐字节重建该权重。

## 当前推理配置

| 项目 | Humble42 汽车候选 |
| --- | --- |
| 输入长边 | 512；4:3 图像的已记录张量形状为 `[1, 3, 384, 512]` |
| 后端 | 原生 PyTorch，CPU FP32，4 个计算线程 |
| 在线汽车工作点 | COCO 类别 2，置信度 0.45；以原槽实际 YAML 为准 |
| 资源依据 | [512 配置收据](../config/car_sim_train20_04_m512_resource_receipt.json) |

训练输入 640 和当前推理输入 512 分别记录。行人仍使用独立预训练 `yolo11n.pt`、320 输入和 2 个计算线程。仿真请求速度为 0.125 倍；仿真时间 FPS、实际墙钟推理耗时和闭环新鲜度分别评价，不能据此声称实时运行已通过。

已有 260 图尺寸回归与独立 worker 时延测量支持当前资源选择，但均属开发资料。236 图回归中新增过跨两车合并大框，原记录保留；尺寸回归通过不抹去该风险，也不替代多目标主动云台的实际闭环结果。

## 来源与许可资料

YOLO 权重和 Ultralytics 的上游来源与许可见[原权重说明](../docs/OPENVINO_CPU_COMPARISON.md)及[Ultralytics 许可页](https://www.ultralytics.com/license)。仿真视觉资产及其 CC0 来源见[资产说明](../docs/VISUAL_ASSETS.md)；视觉资产的 CC0 不改变检测模型的上游许可。最终交付还须索引原训练脚本、数据/标签清单、完整参数、最佳/末轮权重、训练终态和检查记录；本说明不将这些本机工件描述为已上传 GitHub。
