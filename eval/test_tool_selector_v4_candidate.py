"""CPU-only v4 selector syntax, budget, and training/inference prefix tests."""

from __future__ import annotations

import pytest

from tools.audit_tool_contract_candidate import TOKENIZER_SNAPSHOT
from training.tool_contract_candidate import ContractError
from training.tool_schema_inventory import load_public_mcp_tools
from training.tool_selector_v4_candidate import (
    MAX_SELECTION_CHARS, compact_catalog, parse_selection, render_selection,
)


CYLINDER = {"type": "function", "function": {
    "name": "create_cylinder",
    "parameters": {"type": "object", "properties": {
        "radius": {"type": "number"}, "height": {"type": "number"},
    }, "required": ["radius", "height"]},
}}
TOOLS = [CYLINDER]


def test_catalog_exposes_required_fields_without_full_schema() -> None:
    catalog = compact_catalog(TOOLS)
    assert "required: radius, height" in catalog
    assert '"type": "number"' not in catalog


def test_strict_single_bare_json_selection_and_abstention() -> None:
    assert parse_selection('{"tool":"create_cylinder"}<|im_end|>', TOOLS) == "create_cylinder"
    assert parse_selection('{"tool":null}', TOOLS) is None


@pytest.mark.parametrize("bad", [
    '```json\n{"tool":"create_cylinder"}\n```',
    '{"tool":"create_cylinder"}{"tool":"create_cylinder"}',
    '{"tool":"create_cylinder","note":"execute"}',
    '{"tool":"create_cylinder","tool":null}',
    '{"tool":"move_object"}',
    '{"tool":NaN}',
    '{"tool":"create_cylinder"} trailing',
    " " * (MAX_SELECTION_CHARS + 1),
    None,
])
def test_selector_rejects_unsafe_format(bad: str | None) -> None:
    with pytest.raises(ContractError):
        parse_selection(bad, TOOLS)  # type: ignore[arg-type]


@pytest.mark.skipif(not TOKENIZER_SNAPSHOT.is_dir(), reason="pinned tokenizer unavailable")
def test_pinned_tokenizer_prefix_and_budget() -> None:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_SNAPSHOT, local_files_only=True)
    task = "创建一个半径为 1.5、高 3 的测试圆柱"
    prompt = render_selection(tokenizer, task, TOOLS)
    selected = render_selection(tokenizer, task, TOOLS, selected_tool="create_cylinder")
    abstained = render_selection(tokenizer, task, TOOLS, selected_tool=None)
    assert prompt.prompt == selected.prompt == abstained.prompt
    assert selected.full_tokens is not None and selected.full_tokens <= 2048
    assert abstained.full_tokens is not None and abstained.full_tokens <= 2048
    full_inventory = render_selection(tokenizer, task, load_public_mcp_tools())
    assert full_inventory.prompt_tokens + 128 <= 2048
    with pytest.raises(ContractError, match="sequence budget"):
        render_selection(tokenizer, "合成超长任务" * 3000, TOOLS)
