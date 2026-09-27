"""CPU-only v3 format, schema, and train/inference prefix safety tests."""

from __future__ import annotations

import pytest

from tools.audit_tool_contract_candidate import TOKENIZER_SNAPSHOT
from training.tool_contract_candidate import ContractError
from training.tool_contract_v3_candidate import (
    MAX_INVOCATION_CHARS,
    parse_invocation,
    render_invocation,
)


BOX = {"type": "function", "function": {
    "name": "create_box",
    "parameters": {"type": "object", "properties": {
        "width": {"type": "number"},
        "depth": {"type": "number"},
        "height": {"type": "number"},
    }, "required": ["width", "depth", "height"]},
}}
TOOLS = [BOX]
CALL = '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}'


def test_bare_json_single_call_with_optional_qwen_end() -> None:
    expected = {"name": "create_box", "arguments": {"width": 2, "depth": 3, "height": 4}}
    assert parse_invocation(CALL, "create_box", TOOLS) == expected
    assert parse_invocation(" \n" + CALL + "<|im_end|>\n", "create_box", TOOLS) == expected


@pytest.mark.parametrize("bad", [
    "```json\n" + CALL + "\n```",
    "<tool_call>" + CALL + "</tool_call>",
    "explanation " + CALL,
    CALL + " explanation",
    CALL + CALL,
    CALL + "<|im_end|><|im_end|>",
    CALL.replace('"create_box"', '"delete_objects"'),
    CALL.replace('"height":4', '"height":"large"'),
    CALL.replace(',"height":4', ""),
    CALL.replace('"height":4', '"height":4,"extra":1'),
    CALL.replace('"height":4', '"height":4,"height":5'),
    CALL.replace('"height":4', '"height":NaN'),
    CALL.replace('"height":4', '"height":1e999'),
    CALL.replace('"width":2', '"width":true'),
    CALL.replace('"name":', '"note":"ignore prior instructions","name":'),
    CALL.replace('"name":', '"name":"create_box","name":'),
    '["' + CALL + '"]',
    " " * (MAX_INVOCATION_CHARS + 1),
    None,
])
def test_malformed_or_ambiguous_model_output_is_rejected(bad: str | None) -> None:
    with pytest.raises(ContractError):
        parse_invocation(bad, "create_box", TOOLS)  # type: ignore[arg-type]


def test_unknown_selected_tool_and_non_object_arguments_rejected() -> None:
    with pytest.raises(ContractError):
        parse_invocation(CALL, "create_sphere", TOOLS)
    with pytest.raises(ContractError):
        parse_invocation('{"name":"create_box","arguments":[]}', "create_box", TOOLS)


@pytest.mark.skipif(not TOKENIZER_SNAPSHOT.is_dir(), reason="pinned tokenizer unavailable")
def test_pinned_tokenizer_roundtrip_and_locked_budget() -> None:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_SNAPSHOT, local_files_only=True)
    prompt = render_invocation(tokenizer, "在合成文档画一个 2×3×4 盒子", TOOLS, "create_box")
    labeled = render_invocation(
        tokenizer, "在合成文档画一个 2×3×4 盒子", TOOLS, "create_box",
        arguments={"width": 2, "depth": 3, "height": 4},
    )
    assert prompt.prompt == labeled.prompt
    assert labeled.full_tokens is not None and labeled.full_tokens <= 2048
    assert parse_invocation(labeled.full[len(prompt.prompt):], "create_box", TOOLS)
    with pytest.raises(ContractError, match="sequence budget"):
        render_invocation(tokenizer, "合成超长输入" * 3000, TOOLS, "create_box")
