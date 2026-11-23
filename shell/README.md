# shell 脚本说明

本目录为 **Windows `.bat` 入口**（项目约定不使用 `.ps1`）。均在「项目根目录」语义下执行，脚本内部会 `cd` 到上级。

从下载源码到打出绿色包的完整操作步骤，见上级 [`操作步骤说明.md`](../操作步骤说明.md)。

| 脚本 | 功能 | 典型用法 |
|------|------|----------|
| `setup_venv.bat` | 创建 venv 并安装依赖 | 首次开发必跑 |
| `init_master.bat` | （可选）CLI 初始化主密码 | 日常请用 GUI「系统设置→安全」 |
| `run_gui.bat` | 启动桌面 GUI | 日常使用 |
| `run_cli.bat` | 转发 CLI 参数 | `run_cli.bat --help` |
| `run_test.bat` | 跑 pytest | 发版前门禁 |
| `run_smoke.bat` | 本机 Dry-run + 执行冒烟 | 快速自检 |
| `run_publish_demo.bat` | 准备发布演示应用 | 发布功能联调 |
| `run_accept.bat` | 完整版自动化验收冒烟 | 对照验收检查单 |
| `build_release.bat` | PyInstaller 绿色包 | 成品在 `release\AutoExecTool\`（`dist_build` 为中间目录） |
| `start_green.bat` | 绿色包启动器模板 | 打包时复制为产物根目录 `启动.bat` |

**推荐顺序（开发机）：**

```bat
shell\setup_venv.bat
shell\init_master.bat
shell\run_smoke.bat
shell\run_gui.bat
```

每个 `.bat` 文件头部均有 `REM` 注释（功能 / 前提 / 用法），用记事本或 IDE 打开即可查看。
