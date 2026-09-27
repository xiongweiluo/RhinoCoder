"""C5 formal contract identity, routing, and strict parsing tests."""

from __future__ import annotations

import pytest

from tools.audit_tool_contract_candidate import TOKENIZER_SNAPSHOT
from training.c5_contract import (
    CONTRACT_ID,
    CORE_INVOCATION_TOOLS,
    SELECTOR_TOOLS,
    parse_invocation,
    parse_selection,
    render_invocation,
    render_selection,
    selection_route,
)
from training.tool_contract_candidate import ContractError
from training.tool_schema_inventory import load_public_mcp_tools


def test_frozen_scope_and_fail_closed_route() -> None:
    assert CONTRACT_ID == "qwen25-v4-selector-v3-json-invoker-c5-v1"
    assert len(SELECTOR_TOOLS) == 23
    assert len(CORE_INVOCATION_TOOLS) == 12
    assert set(CORE_INVOCATION_TOOLS) < set(SELECTOR_TOOLS)
    assert selection_route(None) == "clarify_or_refuse"
    assert selection_route("create_box") == "invoke_core_tool"
    assert selection_route("get_object_info") == "unsupported_for_c5"


def test_c5_parsers_reject_repairs_and_out_of_scope_invocation() -> None:
    tools = load_public_mcp_tools()
    assert parse_selection('{"tool":"create_box"}', tools) == "create_box"
    with pytest.raises(ContractError):
        parse_selection('```json\n{"tool":"create_box"}\n```', tools)
    with pytest.raises(ContractError):
        parse_invocation('{"name":"get_object_info","arguments":{}}', "get_object_info", tools)


@pytest.mark.skipif(not TOKENIZER_SNAPSHOT.is_dir(), reason="pinned tokenizer unavailable")
def test_c5_training_and_inference_prefixes_are_identical() -> None:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_SNAPSHOT, local_files_only=True)
    tools = load_public_mcp_tools()
    step = "在合成毫米场景创建宽 2、深 3、高 4 的长方体。"
    selection = render_selection(tokenizer, step, tools)
    selection_target = render_selection(tokenizer, step, tools, selected_tool="create_box")
    invocation = render_invocation(tokenizer, step, tools, "create_box")
    invocation_target = render_invocation(
        tokenizer,
        step,
        tools,
        "create_box",
        arguments={"width": 2, "depth": 3, "height": 4},
    )
    assert selection.prompt == selection_target.prompt
    assert invocation.prompt == invocation_target.prompt
    assert parse_selection(selection_target.full[len(selection.prompt) :], tools) == "create_box"
    assert parse_invocation(
        invocation_target.full[len(invocation.prompt) :], "create_box", tools
    )["arguments"] == {"width": 2, "depth": 3, "height": 4}
