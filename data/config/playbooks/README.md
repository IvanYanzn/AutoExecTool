# 业务编排目录（用户 / 现场数据）

本目录存放**现场维护的流程 YAML**，属于 `data/` 用户数据：

- **不随绿色包附带**具体文件（打包只建空目录）
- **默认不入库**（见仓库根 `.gitignore`：忽略本目录下 YAML / 现场说明）
- **升级程序时务必保留**整个 `data\`，勿用新包覆盖

## 建议用法

1. 先熟悉内置示例：`templates/demos/`、`templates/publish/`、`templates/multi-host/`
2. 按 `docs/流程YAML编写指南.md` 编写业务流程
3. 将 YAML 放在本目录（可按环境分子目录，例如 `staging/`、`prod/`）
4. 在「执行流程」中选择对应文件并 Dry-run → 执行

## 敏感信息

- 密码 / 密钥：放在「主机与凭证」（加密于 `data/config/keys/`），不要写进 YAML
- YAML 中的主机地址、路径等属现场配置，故与本目录一并视为用户数据

`use_playbook` 解析顺序：父流程目录 → 本目录 → `templates/`。
