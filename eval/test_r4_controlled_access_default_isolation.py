"""R's versioned experimental entry points must not enter the default route."""

import ast
from pathlib import Path

from plugin.rhino_listener.candidate_v6_live_session import MAX_WRITES
from training.consent_candidate import DELEGATED_HEADLESS_SCOPE


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "tools.r4_controlled_access",
    "tools.r4_v6_live_multistep",
    "plugin.rhino_listener.candidate_v6_live_session",
    "training.controlled_v6_plan",
)


def test_default_entrypoints_do_not_import_isolated_r_route():
    files = list((ROOT / "agent").rglob("*.py"))
    files.append(ROOT / "plugin/rhino_listener/listener_main.py")
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
                imported.extend((node.module or "") + "." + alias.name
                                for alias in node.names)
        assert not any(name.startswith(FORBIDDEN) for name in imported), path


def test_isolated_write_budget_and_scope_are_not_expanded():
    assert MAX_WRITES == 6
    assert DELEGATED_HEADLESS_SCOPE == "isolated_unsaved_headless_mm"
