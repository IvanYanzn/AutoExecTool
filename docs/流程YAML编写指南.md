# AutoExecTool 流程 YAML 编写指南

| 项目 | 说明 |
|------|------|
| 文档版本 | v1.0 |
| 适用产品 | AutoExecTool（自动化执行工具） |
| 读者 | 编排编写人员、运维、以及生成/改写 YAML 的 AI |
| 配套目录 | 业务编排 `data/config/playbooks/`；内置示例 `templates/`；本文在 `docs/` |
| 绿色包路径 | 成品根目录 `docs/流程YAML编写指南.md`；业务流程在 `data/config/playbooks/` |

本文说明「执行流程」所用 YAML 的用途、结构、字段、变量与引用机制，并给出可复制的示例与注意事项。按本文即可手写流程文件；AI 生成时请严格遵循文中 schema 与约束。

---

## 1. YAML 文件是做什么的

一份流程 YAML（Playbook）描述：**按阶段、按步骤自动执行的一组动作**。

典型用途：

- 本机/远程执行命令（Shell / CMD / PowerShell）
- 上传/下载文件、目录复制、服务启停、健康检查
- 现场发版 / 运维编排（构建 → 上传 → 重启等，由用户自行编写）
- 多机经控制端中转拷贝
- 可复用的子流程、指令组拼装

**不是**：随意的配置文件或 Ansible playbook 超集。本工具只识别下文定义的字段与动作；未知顶层键会被忽略或导致校验失败（步骤缺少 `action` / `use_*` 时会报错）。

### 1.1 放在哪里

| 位置 | 说明 |
|------|------|
| `data/config/playbooks/` | **业务编排**（用户数据；可改；升级程序时必须保留整个 `data\`） |
| `templates/` | 内置示例（`demos/`、`publish/`、`multi-host/` 等） |
| 任意路径 | 执行页「选择 YAML」可打开任意 `.yaml` / `.yml` |
| 绿色包 | 只建空的 `data\…` 骨架，**不打包**业务 YAML；示例在 `_internal/templates/` |

### 1.2 怎么执行

1. GUI「执行流程」→ 选择 YAML → 选目标（本机 / 主机 / 主机组）→ 可选「变量集」→ **Dry-run** → **执行**
2. CLI：`shell\run_cli.bat run <playbook.yaml> ...`（以实际 CLI 帮助为准）

执行前引擎会：展开 `use_playbook` → 展开 `use_group` → 渲染 `{{变量}}` → 按阶段串行（阶段内可并行组）逐步执行。

---

## 2. 最小可运行示例

```yaml
name: hello-demo
version: 1
description: 最小示例
variables:
  NAME: World
stages:
  - name: main
    steps:
      - id: say
        action: shell.exec          # Linux/本机类 Unix；Windows 本机请用 cmd.exec
        command: echo Hello-{{NAME}}
      - id: pause
        action: delay
        seconds: 1
```

Windows 本机等价写法：

```yaml
      - id: say
        action: cmd.exec
        command: echo Hello-{{NAME}}
```

---

## 3. 文档结构总览

```text
Playbook YAML
├── name                 # 必填：流程名
├── version              # 可选，默认 1
├── description          # 可选
├── variables            # 可选：默认变量字典
├── command_groups       # 可选：内联指令组
├── on_failure           # 可选：结束通知等
└── stages[]             # 推荐；若省略可用顶层 steps（自动包成 name=main）
    └── stage
        ├── name
        ├── parallel     # 可选：整阶段并行（少用；优先步骤 parallel_group）
        └── steps[]
            ├── id
            ├── action | use_group | use_playbook   # 三选一为主
            ├── 动作参数…（落入 params，见各动作）
            ├── host / timeout_sec / retries / …
            ├── schedule / success_when / parallel_group
            └── playbook_vars（仅 use_playbook）
```

---

## 4. 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | **是** | 流程名称，用于会话记录与日志 |
| `version` | int | 否 | 流程版本号，默认 `1` |
| `description` | string | 否 | 人类可读说明 |
| `variables` | map | 否 | 默认变量；子流程可被父级 / `playbook_vars` 覆盖；运行时再被「变量集」与 `host.*` 覆盖（见 §9.2） |
| `command_groups` | map | 否 | 内联指令组定义，键为组名 |
| `stages` | list | 建议 | 阶段列表；无则看 `steps` |
| `steps` | list | 二选一 | 无 `stages` 时，自动变为单阶段 `main` |
| `on_failure` | map | 否 | 结束时可选 Webhook：`notify_url`（失败）、`notify_on_success_url`（成功） |

`on_failure` 示例：

```yaml
on_failure:
  notify_url: "https://example.com/hooks/fail"
  notify_on_success_url: "https://example.com/hooks/ok"
```

---

## 5. 阶段（stage）

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 阶段名（日志里显示「阶段=…」） |
| `steps` | list | 本阶段步骤 |
| `parallel` | bool | `true` 时本阶段步骤并行（慎用）；更常用步骤级 `parallel_group` |

阶段之间**始终串行**：上一阶段全部结束后才进入下一阶段。

---

## 6. 步骤（step）通用字段

每个步骤必须能确定「做什么」：

- 写 `action: <动作类型>`，或
- 写 `use_group: <组名>`，或
- 写 `use_playbook: <路径>`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 步骤 ID；日志、重跑、展开前缀都依赖它。建议英文蛇形：`scp_upload` |
| `action` | string | 动作类型，如 `cmd.exec`、`file.upload`（见 §8） |
| `use_group` | string | 引用指令组名（见 §10） |
| `use_playbook` | string | 引用子流程 YAML（见 §11） |
| `playbook_vars` / `variables` | map | 仅配合 `use_playbook`：覆盖子流程变量（`variables` 为别名） |
| `host` | string | 步骤级目标主机：库存主机 **名称** / **id** / `local`/`本机`；支持 `{{VAR}}`。空则用执行页会话默认目标 |
| `timeout_sec` | number | 本步超时秒数；不写则不按此字段限时（连接器/动作另有默认） |
| `retries` | int | 失败重试次数，默认 `0` |
| `retry_interval_sec` | int | 重试间隔秒，默认 `3` |
| `schedule` | map | 等到指定时刻再执行（见 §7） |
| `success_when` | map | 成功条件（见 §7） |
| `parallel_group` | string | 同阶段同组名的步骤并行执行 |

**步骤参数约定：**  
除上表「元数据」外，步骤上的其它键（如 `command`、`local`、`remote`、`seconds`）全部作为该动作的 **params** 传入。

---

## 7. 调度与成功条件

### 7.1 `schedule`（步骤开跑前等待）

> 与 UI「任务调度」页的 **流程级 Cron** 不同：Cron 是到点后**从头跑整份流程**；
> 这里的 `schedule` 是流程已经跑到本步后，**再等到指定时刻**才真正执行该步。

```yaml
schedule:
  execute_at: "23:30"              # 或 "23:30:00"，或 ISO 日期时间
  timezone: "Asia/Shanghai"        # 默认 Asia/Shanghai
  if_past: "run_immediately"       # run_immediately | fail | skip
  max_wait_sec: 3600               # 可选：等待超过则失败
```

| `if_past` | 含义 |
|-----------|------|
| `run_immediately` | 已过点则立刻执行（默认） |
| `fail` | 已过点则失败 |
| `skip` | 已过点则跳过本步 |

### 7.2 `success_when`

未配置时：以动作返回的 `success` 为准（通常即 `exit_code == 0`）。

```yaml
success_when:
  exit_code: 0
  # 或 exit_codes: [0, 1]
  stdout_contains: "ok"
  stdout_not_contains: "error"
  stderr_contains: "warn"    # 可选：stderr 须包含
```

条件为 **且** 关系：写出的每一项都要满足。

---

## 8. 内置动作一览（action）

别名：`shell`→`shell.exec`，`cmd`→`cmd.exec`，`powershell`→`powershell.exec`。

### 8.1 命令类

| action | 适用 | 主要参数 | 说明 |
|--------|------|----------|------|
| `shell.exec` | Linux 远端 / 类 Unix 本机 | `command` | 在目标上执行 shell |
| `cmd.exec` | **Windows 本机**（或 Windows 目标走 cmd） | `command` | `shell=True` 经 cmd；适合 `cd /d`、`scp`、本机 OpenSSH |
| `powershell.exec` | Windows | `command` | PowerShell |

```yaml
- id: build
  action: cmd.exec
  timeout_sec: 3600
  command: >-
    cd /d "{{JAVA_ROOT}}"
    && mvn clean package -pl my-app -am -DskipTests
```

**选型建议**

| 场景 | 推荐 |
|------|------|
| Windows 控制端跑本机 scp/ssh/mvn/pnpm | `cmd.exec` |
| SSH 到 Linux 后在远端执行 | 目标选 SSH 主机 + `shell.exec` |
| Windows 远端 WinRM | `powershell.exec` / `shell.exec` 视连接器而定 |

### 8.2 等待类

| action | 参数 | 说明 |
|--------|------|------|
| `delay` | `seconds` 或 `sec` | 睡眠 N 秒 |
| `wait.until` | `execute_at` 或 `at` | 由引擎按 schedule 语义等待（也可写在步骤 `schedule`） |

### 8.3 文件类

| action | 参数 | 说明 |
|--------|------|------|
| `file.upload` | `local`, `remote` | 本机→目标主机 |
| `file.download` | `remote`, `local` | 目标→本机 |
| `script.upload_and_run` | `local`, `remote`, 可选 `command` | 上传后执行 |
| `fs.copy_tree` | `src`, `dest`, 可选 `ok_if_missing` | 目录/文件树复制 |

### 8.4 其它

| action | 参数 | 说明 |
|--------|------|------|
| `process.wait` | `name`, `appear`, `retries`, `interval_sec` | 等进程出现/退出 |
| `condition` | `expression` | 简单条件：`var==value` / `var!=value` / 真值变量名 |
| `http.healthcheck` | `url`, `expect_status`, `retries`, `interval_sec` | HTTP 探测 |
| `notify` | `url`, `message`, 可选 `payload` | Webhook POST |
| `service.control` | `service`, `operation` | `start`/`stop`/`restart`/`status` |

插件动作（若加载）：如 `sample.echo`，以「系统设置 / 插件」与首页目录为准。

---

## 9. 变量与参数引用

### 9.1 写法

在**字符串**中使用双花括号：

```text
{{VAR_NAME}}
{{host.address}}
{{host.name}}
```

引擎用正则替换；支持点分路径（先按扁平键查找，再按嵌套 dict 查找）。

### 9.2 变量从哪里来（优先级从高到低）

展开 / 合并阶段（写入流程变量后再执行）：

1. **`use_playbook` 步骤上的 `playbook_vars` / `variables`**
2. **父流程 `variables`**
3. **子流程自身 `variables`**（同名被父级覆盖）

运行时（每步渲染前）：

4. **执行页所选「变量集」**（覆盖流程变量同名键）
5. **当前步骤目标主机**：`host` / `host.address` / `host.name` / `host.id`（会覆盖变量集里同名的 `host.*`）
6. **步骤输出**：动作 `outputs` → `steps.<stepId>.<key>` 与顶层 `<key>`（供后续步骤使用）

### 9.3 变量集（GUI）

「变量与指令组 → 变量集」保存 YAML **字典**，执行时在下拉框选择，用于覆盖环境差异（主机、路径、分支），无需改流程文件。

### 9.4 编写建议

- 路径、主机、分支、构建命令尽量放进 `variables`，步骤里只写 `{{XXX}}`
- 不要在密钥类内容里硬编码密码；用「主机与凭证」绑定
- Windows 路径在 YAML 里可用正斜杠：`D:/codespace/...`

---

## 10. 指令组（use_group）

**指令组 = 可复用的 steps 列表**（一步或多步），不是完整流程。

### 10.1 内联定义

```yaml
name: group-demo
command_groups:
  greet_block:
    steps:
      - id: wait_a_bit
        action: delay
        seconds: 1
      - id: say
        action: delay
        seconds: 0
stages:
  - name: main
    steps:
      - id: use_greet
        use_group: greet_block
```

展开后步骤 id 形如：`use_greet.wait_a_bit`、`use_greet.say`。

### 10.2 库内指令组

在「变量与指令组 → 指令组」保存同结构 YAML（须含 `steps`）。流程中：

```yaml
- id: do_reload
  use_group: nginx_reload_block
```

解析顺序：先流程内 `command_groups`，再按名查数据库。

### 10.3 与子流程对比

| | `use_group` | `use_playbook` |
|--|-------------|----------------|
| 内容 | 仅 steps | 完整 playbook（stages、variables、可再嵌套） |
| 存储 | 内联或数据库 | 独立 `.yaml` 文件 |
| 适合 | 小片段复用 | 大流程拆分（构建/上传/一键） |

---

## 11. 子流程（use_playbook）

### 11.1 引用方式

```yaml
stages:
  - name: 本地打包
    steps:
      - id: build
        use_playbook: build_local.yaml
        # 可选覆盖：
        # playbook_vars:
        #   BRANCH: "main"
  - name: 上传重启
    steps:
      - id: deploy
        use_playbook: upload_restart.yaml
```

### 11.2 路径解析顺序

1. 绝对路径且存在  
2. 相对**父流程文件所在目录**  
3. 相对 `data/config/playbooks/`（业务编排，优先于内置）  
4. 相对 `templates/`（内置示例）  
5. 若只写文件名，依次在 playbooks、templates 下按文件名递归匹配  

同目录引用直接写文件名即可；跨目录可用 `subdir/xxx.yaml`（相对 playbooks 或 templates 根）。

### 11.3 展开规则

- 子流程各阶段步骤**展平**进父流程当前阶段（按引用点插入）
- 新步骤 id：`引用步id.子阶段名.子步骤id`
- 变量：`playbook_vars` > 父 `variables` > 子 `variables`
- 引用步的 `host` / `schedule`（仅落到展开后的首步）可向下继承
- 禁止循环引用；最大嵌套 **8** 层
- 时间线有「引用」类别日志

---

## 12. 步骤级主机（host）

```yaml
variables:
  SRC_HOST: "源文件服务器"
  DST_HOST: "目标应用服务器"

stages:
  - name: 拉取
    steps:
      - id: download_from_src
        host: "{{SRC_HOST}}"
        action: file.download
        remote: "{{REMOTE_SRC}}"
        local: "{{LOCAL_TMP}}"
  - name: 推送
    steps:
      - id: upload_to_dst
        host: "{{DST_HOST}}"
        action: file.upload
        local: "{{LOCAL_TMP}}"
        remote: "{{REMOTE_DST}}"
```

要点：

- `host` 填库存中的**名称或 id**，或 `local` / `本机`
- 执行页仍要选一个默认目标；未写 `host` 的步骤用该默认目标
- 方案 A（本机 OpenSSH scp/ssh）：默认目标选本机，命令里写 `ssh/scp user@host`
- 方案 B（Paramiko/凭证）：步骤或默认目标选 SSH 主机 + `file.upload` / `shell.exec`

---

## 13. 并行

**同阶段并行组（推荐）：**

```yaml
stages:
  - name: parallel-main
    steps:
      - id: a
        action: cmd.exec
        command: echo a
        parallel_group: g1
      - id: b
        action: cmd.exec
        command: echo b
        parallel_group: g1
```

同名 `parallel_group` 的步骤并行；组与组、无组步骤按书写顺序串行。  
阶段级 `parallel: true` 也可整阶段并行，但可读性较差，优先用 `parallel_group`。

---

## 14. Windows 本机 `cmd.exec` + `ssh "..."` 专项约束

发版模板（方案 A）常用：本机 `cmd.exec` 调用 `ssh`/`scp`。必须遵守：

1. **`ssh "远程脚本"` 的双引号内不要出现真实换行**  
   YAML 使用 `>-` 时，**比内容多缩进的行会保留 `\n`**，导致远端 bash：`syntax error: unexpected end of file`。  
   → 远程脚本写成**同一缩进的一行**（用 `;` 连接），或确保折叠后无嵌套缩进换行。

2. **`%Y%m%d` 等会被 Windows cmd 当环境变量吞掉**  
   → 避免在经 cmd 传递的命令里直接写 `%Y...`；可用 `^%Y^%m...`，或改用不含 `%` 的时间戳策略。

3. **备份策略按环境自行约定**（测试可简化；生产建议先备份再覆盖）。  
   业务 YAML 由现场维护在 `data/config/playbooks/`，产品不附带具体发版流程。

正确示例（单行远程脚本）：

```yaml
- id: remote_overwrite
  action: cmd.exec
  command: >-
    ssh {{SSH_OPTS}} {{REMOTE_USER}}@{{REMOTE_HOST}}
    "set -e; mkdir -p {{REMOTE_JAVA_DIR}}; cp -f {{REMOTE_TMP_JAR}} {{REMOTE_JAR}}; echo ok"
```

---

## 15. 推荐文件头注释（给人与 AI）

```yaml
# =============================================================================
# <一句话标题>
# =============================================================================
# 作用：…
# 目标：本机 | SSH 主机名…
# 前置：免密 / 凭证 / 路径…
# 能否随便执行：✅ 可以 | ⚠️ 需改变量 | ❌ 生产危险
# =============================================================================
name: ...
```

---

## 16. 完整字段速查（AI / 校验用）

### 16.1 Playbook

```yaml
name: string                 # required
version: int                 # default 1
description: string
variables: { string: any }
command_groups:
  <group_name>:
    steps: [ Step ]
on_failure:
  notify_url: string
  notify_on_success_url: string
stages:
  - name: string
    parallel: bool
    steps: [ Step ]
# 或者
steps: [ Step ]              # 自动包成 stages[0].name=main
```

### 16.2 Step

```yaml
id: string
action: string               # 与 use_group / use_playbook 三选一为主
use_group: string
use_playbook: string
playbook_vars: { string: any }
variables: { string: any }   # playbook_vars 别名
host: string
timeout_sec: number
retries: int
retry_interval_sec: int
schedule:
  execute_at: string
  timezone: string
  if_past: run_immediately|fail|skip
  max_wait_sec: number
success_when:
  exit_code: int
  exit_codes: [int]
  stdout_contains: string
  stdout_not_contains: string
  stderr_contains: string
parallel_group: string
# 其余键 → 动作 params，例如：
command: string
local: string
remote: string
seconds: number
url: string
# ...
```

### 16.3 生成检查清单（AI 必过）

- [ ] 有 `name`
- [ ] 每个步骤有 `action` 或 `use_group` 或 `use_playbook`
- [ ] 动作必填参数齐全（见 §8）
- [ ] Windows 本机命令用 `cmd.exec`，Linux 远端用 `shell.exec`
- [ ] 变量占位符为 `{{NAME}}`，且在 `variables` / 变量集 / playbook_vars 有来源
- [ ] `use_playbook` 路径在同目录、`data/config/playbooks` 或 `templates` 可解析
- [ ] 经本机 cmd 的 `ssh "..."` 远程脚本无「引号内真实换行」
- [ ] 生产流程默认勿清空重要目录；备份策略与环境一致
- [ ] 文件头注明目标环境与能否随便执行

---

## 17. 场景模板索引

| 需求 | 参考文件 |
|------|----------|
| 本机冒烟 | `templates/demos/local_smoke.yaml`、`local_smoke_windows.yaml` |
| 指令组 | `templates/demos/group_demo.yaml` |
| 并行 + success_when | `templates/demos/parallel_success_demo.yaml` |
| 多机 host | `templates/multi-host/multi_host_copy_via_controller.yaml` |
| 目录发布/回滚 | `templates/publish/` |
| 现场业务发版 | 自行编写，放入 `data/config/playbooks/`（可分子目录；不随包/不入库） |

---

## 18. 常见错误

| 现象 | 原因 | 处理 |
|------|------|------|
| 步骤缺少 action | 未写 action/use_group/use_playbook | 补全 |
| 未找到子流程 | 路径不对 | 用同目录文件名或 `subdir/file.yaml` |
| 未找到指令组 | 组名未定义/未保存 | 检查 `command_groups` 或资产页 |
| `{{X}}` 原样出现 | 变量未定义 | 补 variables / 选变量集 |
| bash unexpected EOF | ssh 引号内含真实换行 | 改单行远程脚本 |
| cmd 里日期错乱 | `%Y` 被 cmd 吞掉 | 转义或换时间戳方案 |
| 上传成功但服务仍旧 | 只 restart 未 rebuild 镜像 | Java 发版需 `docker compose build` 再 `up` |
| 连接失败 | 凭证未绑定/未解锁主密码 | 主机与凭证页配置 |

---

## 19. 版本与扩展

- 动作列表以运行中「首页 / 动作目录」及 `actions/builtin.py`、插件为准；本文随内置动作更新。
- 自定义插件动作：实现并放入 `plugins/`，参数同样写在步骤上（非元数据键进入 params）。

---

**文档维护：** 变更 loader / 动作 schema 时，请同步更新本文 §4–§8、§16。
