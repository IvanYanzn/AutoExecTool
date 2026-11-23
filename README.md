# AutoExecTool

通用自动化任务编排执行工具：连接本机 / SSH / WinRM 主机，用 YAML（或 GUI）编排命令与发布流程并执行，覆盖服务发布、回滚、定时任务与会话日志。

**从源码到可运行成品（一步步照做）：** 见 [`操作步骤说明.md`](操作步骤说明.md)。

设计细节见上级目录 [`doc/软件设计方案.md`](../doc/软件设计方案.md)；发版勾选见 [`doc/完整版验收检查单.md`](../doc/完整版验收检查单.md)。

## 能做什么

| 能力 | 说明 |
|------|------|
| 主机与凭证 | 主机 / 主机组 CRUD；Local、SSH、WinRM；主密码加密凭证（密码 / SSH 密钥）；生成密钥（私钥进保险库，公钥在 `data/config/keys/`）；安装公钥到主机；CSV 导入导出 |
| 流程编排 | 阶段 / 步骤 / 指令组；变量与变量集；成功条件、重试、计划时间、Dry-run、并行组 |
| 内置动作 | shell / PowerShell / cmd、文件上下传、目录拷贝、服务控制、健康检查、通知、延时等 |
| 编辑方式 | GUI：流程画布 + 节点属性 + YAML；CLI 直接跑 YAML |
| 执行与恢复 | 后台执行不卡界面；会话落库；**时间线日志**（会话/阶段/节点/执行/返回/输出/错误/引用等）；脱敏；Interrupted；整单 / 从失败步重跑 |
| 发布中心 | 应用 / 环境 / 制品、发布与一键回滚；Windows / Linux 目录模板 |
| 调度与扩展 | 仅一次 / 间隔与频率预设 / Cron；`plugins/` 加载外部动作；Webhook 通知（`notify`） |
| 系统 | data 备份恢复、日志保留清理、绿色包（内置运行时） |

## 两种使用方式

### 1）最终用户（绿色包）

1. 运行 `shell\build_release.bat`（开发机）
2. 打开成品目录 **`release\AutoExecTool\`**（不是 `dist_build` 那一层；`dist_build` 里的 `work`、`.spec` 是打包中间文件）
3. 双击 `启动.bat` 或 `AutoExecTool.exe`（无需安装 Python）
4. 需要远程凭证时：界面「系统设置 → 安全」设置主密码（本地执行可不设）
5. 分发时只需压缩 `release\AutoExecTool` 整个文件夹

**「冷机可启动」**：指把绿色包拷到**没装 Python 的电脑**解压后能打开界面——这是发版人工复核项，不是缺功能。程序已按冻结环境解析 `data/`、模板与插件路径；换机验证杀毒拦截、解压完整性等即可。

### 2）开发 / 本机构建

**环境：** Python 3.11+，Windows / Linux（日常脚本以 Windows `.bat` 为主）。

```bat
shell\setup_venv.bat
shell\run_smoke.bat
shell\run_gui.bat
```

手动等价：

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
autoexectool --help
autoexectool-gui
```

## 日常使用说明

### 图形界面（推荐）

```bat
shell\run_gui.bat
```

左侧导航大致对应：

- **执行流程**：多标签；每标签独立选 YAML / 目标 / 日志，可并行执行不同流程  
- **步骤级主机**：YAML/`host` 可引用库存主机；多机示例见 `templates/multi-host/`  
- **流程引用**：`use_playbook` 嵌套子流程；内置示例见 `templates/`；现场业务 YAML 放 `data/config/playbooks/`  

  - **Dry-run**：只预览步骤，不真正执行  
  - **执行**：后台跑编排；界面 Tail 时间线；任务开始/结束会弹出提示；可切到其他页再回来看  
  - 注意：整份编排跑在所选「目标」上。若流程是本机构建再 `ssh`/`scp` 到远端，目标应选 **本机**，不要选远端主机  
- **流程编排**：实时渲染流程画布（多阶段/节点）、右侧编辑节点属性（含 `schedule`）、YAML 双向同步与校验  
- **主机与凭证**：主机、凭证、主机组（远程凭证需先在设置中解锁保险库）  
- **变量与指令组**：复用环境变量集、`use_group` 指令组  
- **发布中心**：准备演示应用 → 发布 → 一键回滚  
- **执行记录**：会话列表、步骤摘要、**同款时间线回看**；整单 / 从失败步重跑  
- **任务调度**：仅一次 / 间隔 / 频率预设 / Cron；多条可并行触发；执行会话与时间线日志同手动（trigger=`schedule`）  
- **系统设置**：主密码、备份与日志清理  

### 命令行

参数透传入口：

```bat
shell\run_cli.bat --help
```

常用示例：

```bat
shell\run_cli.bat version
shell\run_cli.bat run templates\demos\local_smoke_windows.yaml --dry-run
shell\run_cli.bat run templates\demos\parallel_success_demo.yaml
shell\run_cli.bat host list
shell\run_cli.bat host-group add --name web --host-ids <id1>,<id2>
shell\run_cli.bat publish demo
shell\run_cli.bat publish list
shell\run_cli.bat publish deploy --app-id ... --env-id ... --package-id ...
shell\run_cli.bat publish rollback --app-id ... --env-id ...
shell\run_cli.bat schedule add --name smoke --at 2026-11-23T17:30 --playbook templates\demos\group_demo.yaml
shell\run_cli.bat schedule add --name daily --cron "30 17 * * *" --playbook templates\demos\group_demo.yaml
shell\run_cli.bat plugins
shell\run_cli.bat backup
shell\run_cli.bat logs-cleanup --retain-days 30
```

内置示例在 `templates\`（冒烟、指令组、并行、发布/回滚等，随包分发）。  
现场业务编排放 `data\config\playbooks\`（用户数据：不入库、绿色包仅空目录；升级勿覆盖整个 `data\`）。  
YAML 编写说明：`docs\流程YAML编写指南.md`（打包后在成品根目录 `docs\`）。

## shell 脚本一览

更细的注释见 [`shell/README.md`](shell/README.md)（各 `.bat` 文件头也有 REM 说明）。

| 脚本 | 作用 |
|------|------|
| `shell\setup_venv.bat` | 创建 venv 并安装依赖 |
| `shell\init_master.bat` | （可选）CLI 设主密码；日常用「系统设置→安全」 |
| `shell\run_gui.bat` | 启动桌面界面 |
| `shell\run_cli.bat` | 转发 CLI 参数 |
| `shell\run_test.bat` | 运行 pytest |
| `shell\run_smoke.bat` | 本地 Dry-run + 执行冒烟 |
| `shell\run_publish_demo.bat` | 准备发布演示应用 |
| `shell\run_accept.bat` | 完整版验收冒烟 |
| `shell\build_release.bat` | 打绿色包 → 成品 **`release\AutoExecTool\`**（`dist_build` 为中间产物） |

## 数据目录

默认使用程序旁 `data/`（`config` / `db` / `logs` / `backups` / `packages` 等）。配置与会话以 **SQLite** 为主；每次执行在  
`data/logs/executions/{session_id}/` 下落盘：

| 文件 | 内容 |
|------|------|
| `timeline.jsonl` | 可追溯时间线（带类别，供界面实时 Tail / 执行记录回看） |
| `{step_id}.out` / `.err` | 步骤完整 stdout / stderr（步骤结束后写入） |
| `meta.txt` | 会话结束状态摘要 |

字段示例与类别约定见设计方案 **§3.5.2**。  
**完整版范围外（增强）**：执行报告 HTML/MD/ZIP 导出、命令执行中逐行流式 Tail——见 §3.5.3 / §11.3 与验收检查单「增强项」。

业务编排目录约定：
- 路径：`data\config\playbooks\`（可按环境分子目录，如 `staging\`、`prod\`）
- 性质：现场维护的用户数据；Git / 绿色包均不附带具体 YAML
- 入门：先跑 `templates\demos\`，再按 `docs\流程YAML编写指南.md` 编写并放入上述目录

数据库迁移可选：`alembic upgrade head`（日常启动时由 `create_all` + 轻量补列自动就绪）。

## 质量门禁

```bat
shell\run_test.bat
shell\run_accept.bat
```

全部通过后再宣称完整版可用，并人工勾选验收检查单剩余项。

## License

本项目为**专有软件**（见根目录 [`LICENSE`](LICENSE)）：允许下载与自用，未经授权不得再分发或作为产品转售。欢迎提 Issue；默认不接受对外贡献合并。
