# 发布 / 回滚模板

供「**发布中心**」内部调用（按文件名在 templates 下查找），演示「备份 → 覆盖部署 / 从备份回滚」。

| 文件 | 作用 | 随便执行？ |
|------|------|------------|
| `publish_dir_local.yaml` | 本机目录发布 | ⚠️ 勿空跑；走发布中心 |
| `publish_dir_linux.yaml` | Linux 目录发布 | ❌ 默认路径危险，须改变量 |
| `rollback_dir_local.yaml` | 本机回滚 | ⚠️ 勿空跑；走发布中心 |
| `rollback_dir_linux.yaml` | Linux 回滚 | ❌ 默认路径危险，须改变量 |

依赖变量：`DEPLOY_DIR`、`PACKAGE_PATH`、`BACKUP_REF`（发布中心会注入）。
