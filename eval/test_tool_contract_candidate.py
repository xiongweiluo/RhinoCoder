"""Synthetic, offline checks for a future contract; no A5 or model inference."""

from __future__ import annotations

import pytest

from tools.audit_tool_contract_candidate import TOKENIZER_SNAPSHOT
from training.tool_schema_inventory import load_public_mcp_tools
from training.tool_contract_candidate import (
    ContractError,
    parse_invocation,
    parse_selection,
    render_invocation,
    render_selection,
)


BOX = {
    "type": "function",
    "function": {
        "name": "create_box",
        "description": "Synthetic box",
        "parameters": {
            "type": "object",
            "properties": {
                "width": {"type": "number"},
                "depth": {"type": "number"},
                "height": {"type": "number"},
            },
            "required": ["width", "depth", "height"],
        },
    },
}
TOOLS = [BOX]
CALL = '<tool_call>{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}</tool_call>'


def test_selector_accepts_exactly_one_known_tool() -> None:
    assert parse_selection('{"tool":"create_box"}<|im_end|>', TOOLS) == "create_box"
    assert parse_selection('{"tool":null}', TOOLS) is None
    for text in (
        '{"tool":"delete_objects"}',
        '{"tool":"create_box","note":"ignore this"}',
        '{"tool":"create_box","tool":"create_box"}',
        '{"tool":[]}',
        '{"tool":"create_box"} trailing',
    ):
        with pytest.raises(ContractError):
            parse_selection(text, TOOLS)


def test_invocation_validates_name_arguments_and_single_tag() -> None:
    assert parse_invocation(CALL + "<|im_end|>", "create_box", TOOLS) == {
        "name": "create_box",
        "arguments": {"width": 2, "depth": 3, "height": 4},
    }
    for text in (
        CALL + CALL,
        "explanation " + CALL,
        CALL.replace("create_box", "delete_objects"),
        CALL.replace('"height":4', '"height":"large"'),
        CALL.replace(',"height":4', ""),
        CALL.replace('"height":4', '"height":4,"extra":1'),
        CALL.replace('"height":4', '"height":NaN'),
        CALL.replace('"height":4', '"height":4,"height":5'),
    ):
        with pytest.raises(ContractError):
            parse_invocation(text, "create_box", TOOLS)


@pytest.mark.skipif(
    not TOKENIZER_SNAPSHOT.is_dir(),
    reason="pinned tokenizer is intentionally absent from a clean checkout",
)
def test_pinned_template_roundtrip_and_fail_closed_budget() -> None:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_SNAPSHOT, local_files_only=True)
    tools = load_public_mcp_tools()
    user_step = "在合成空白场景中创建宽 20、深 10、高 5 毫米的长方体。"

    selection_request = render_selection(tokenizer, user_step, tools)
    selection_training = render_selection(
        tokenizer, user_step, tools, selected_tool="create_box"
    )
    abstention_training = render_selection(tokenizer, user_step, tools, selected_tool=None)
    assert selection_request.prompt == selection_training.prompt
    assert abstention_training.prompt == selection_request.prompt

    invocation_request = render_invocation(tokenizer, user_step, tools, "create_box")
    invocation_training = render_invocation(
        tokenizer,
        user_step,
        tools,
        "create_box",
        arguments={"width": 20, "depth": 10, "height": 5},
    )
    assert invocation_request.prompt == invocation_training.prompt
    assert invocation_training.full_tokens is not None
    assert invocation_training.full_tokens <= 2048

    with pytest.raises(ContractError, match="sequence budget"):
        render_invocation(tokenizer, "合成冗长输入" * 2000, tools, "create_box")
