from __future__ import annotations

from pathlib import Path

from autoexectool.app.container import build_container
from autoexectool.publish.service import PublishService


def test_deploy_and_rollback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    svc = PublishService(container)
    # templates 路径基于包位置，不受 tmp 影响
    app_id, env_id, package_id = svc.ensure_demo_app()

    deploy_dir = Path(svc.list_apps()[0].deploy_dir)
    # 预置旧版本内容，便于验证备份与回滚
    (deploy_dir / "OLD.txt").write_text("old\n", encoding="utf-8")

    result = svc.deploy(app_id=app_id, env_id=env_id, package_id=package_id)
    assert result["status"] == "Succeeded"
    assert (deploy_dir / "APP_VERSION.txt").read_text(encoding="utf-8").startswith("1.0.0")
    assert Path(result["backup_ref"]).exists()
    assert (Path(result["backup_ref"]) / "OLD.txt").exists()

    # 污染部署目录后再回滚
    (deploy_dir / "APP_VERSION.txt").write_text("broken\n", encoding="utf-8")
    rb = svc.rollback(app_id=app_id, env_id=env_id)
    assert rb["status"] == "Succeeded"
    # 回滚恢复的是发布前备份（含 OLD.txt），不是制品 1.0.0
    assert (deploy_dir / "OLD.txt").exists()


def test_publish_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOEXECTOOL_DATA", str(tmp_path / "data"))
    container = build_container(tmp_path / "data")
    svc = PublishService(container)
    app_id, env_id, package_id = svc.ensure_demo_app()
    result = svc.deploy(
        app_id=app_id, env_id=env_id, package_id=package_id, dry_run=True
    )
    assert result["dry_run"] is True
    assert any("backup" in x.lower() or "fs.copy_tree" in x for x in result["plan"])
