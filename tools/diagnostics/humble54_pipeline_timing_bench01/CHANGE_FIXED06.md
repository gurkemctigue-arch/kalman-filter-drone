# fixed06：动态脚本执行前注册模块

short02 已真实退出：四个算法节点正常退出，回放器在加载原 `evaluate_stage1_flight.py` 时失败。该文件使用 future annotations 和 dataclass；动态加载器未先把新模块登记到 `sys.modules`，使 Python 3.10 dataclass 的类型解析找不到模块命名空间。原失败输出继续保留。

运行源码仅在原 `module_from_spec()` 与 `exec_module()` 之间增加 `sys.modules[spec.name] = helper`。bench.py 同文件没有第二处按文件动态加载。observer.py 的固定 c7 探针另有动态 exec；该精确固定源码没有 dataclass，且先前实际运行已通过 runtime gate，本次不改它。

回归从临时目录真实动态加载一个带 future annotations、dataclass 和 ClassVar 的 Python 文件，经生产 `replay_worker()` 的实际导入语句执行，随后在接触录包前主动停止；不用导入桩替代这条路径。现有 22 项测试与该回归一起运行，另用归档 fixed05 原回放器作负对照。结果见 `validation_windows06.json`。

fixed05 的全部清单源、测试记录和 CURRENT 已逐字节归档到 `archive_fixed05/`。归档收据 SHA 为 `3e25c1b8a64b44ac116be43014c65e2297ac2a159e1d382c6d05dd9f2c7948e0`。本次不修改冻结算法源、原回放输出、消息链路、timeout、清理门或计时结论，也不启动 native。下一次原生短回放应使用独立的新输出目录。
