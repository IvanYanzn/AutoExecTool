# 演示 / 冒烟模板

这些是**功能演示**，用来验证引擎能力，不是业务发布。

| 文件 | 作用 | 随便执行？ |
|------|------|------------|
| `local_smoke_windows.yaml` | Windows 本机 PowerShell 冒烟 | ✅ 可以 |
| `local_smoke.yaml` | Linux/类 Unix shell 冒烟 | ✅ 可以 |
| `group_demo.yaml` | `use_group` 指令组展开 | ✅ 可以 |
| `parallel_success_demo.yaml` | 并行组 + stdout 成功条件（Windows cmd） | ✅ 可以（Windows） |

执行页目标选 **本机**，先 Dry-run 再执行即可。
