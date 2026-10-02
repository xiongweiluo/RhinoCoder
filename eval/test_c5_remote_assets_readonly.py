import ast

from tools.check_c5_remote_assets_readonly import REMOTE


def test_remote_probe_is_explicitly_readonly_and_does_not_import_model_runtime():
    tree = ast.parse(REMOTE)
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imports.intersection({"torch", "transformers", "peft"})
    assert not any(isinstance(node, ast.Assert) for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr in {"write_text", "write_bytes", "unlink", "mkdir", "load_model", "generate"}
                   for node in ast.walk(tree))
    assert "owner-private-generations" not in REMOTE and "final/public" not in REMOTE
    assert "checkpoint-132" in REMOTE and 'p.open("rb")' in REMOTE
