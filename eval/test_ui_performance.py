from pathlib import Path

from tools.check_ui_performance import BUDGETS, audit_ui_bundle


def test_ui_bundle_budget_accepts_small_assets(tmp_path: Path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "index.html").write_text("<main>RhinoCoder</main>", encoding="utf-8")
    (assets / "index.js").write_text("console.log('demo')", encoding="utf-8")
    (assets / "index.css").write_text("body{margin:0}", encoding="utf-8")

    result = audit_ui_bundle(tmp_path)

    assert result["passed"]
    assert result["measurements"]["javascript_gzip_bytes"] < BUDGETS["javascript_gzip_bytes"]


def test_ui_bundle_budget_rejects_missing_build(tmp_path: Path):
    result = audit_ui_bundle(tmp_path)
    assert not result["passed"]
    assert "dist/index.html" in result["findings"][0]
