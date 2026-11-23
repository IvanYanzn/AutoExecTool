# 流程模板目录（内置只读示例）

本目录为**产品自带**示例与通用模板，随程序打包到 `_internal/templates/`。  

**业务发版编排**在 `data/config/playbooks/`（用户数据）：发版包**不附带**具体 YAML，只初始化空目录；升级生产机时勿覆盖整个 `data\`。

**编写规范：** `docs/流程YAML编写指南.md`

| 目录 | 内容 | 随便执行？ |
|------|------|------------|
| `demos/` | 冒烟与能力演示 | ✅ 可随便跑（本机、无业务副作用） |
| `publish/` | 发布中心用的目录发布/回滚 | ⚠️/❌ 勿空跑，走发布中心或改安全路径 |
| `multi-host/` | 多机经控制端拷贝 | ⚠️ 需库存主机与正确路径 |

现场业务 YAML 请放 `data/config/playbooks/`（可自建子目录），勿放回本目录（升级 `templates` 可能被覆盖）。  
`use_playbook` 解析顺序：父流程目录 → `data/config/playbooks` → `templates`。
