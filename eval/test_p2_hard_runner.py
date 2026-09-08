from eval.p2_hard import _fixture_equal, _frozen_v1_system_prompt, _is_infrastructure_result


def _snapshot(center, size=(30, 70, 10)):
    return {
        "objects": {
            "panel": {
                "exists": True,
                "object_id": "stable-id",
                "bbox": {"center": list(center), "size": list(size)},
                "name": "RotatedPanel",
                "layer": "Default",
                "color": [120, 120, 120],
                "groups": [],
            }
        }
    }


def test_geometry_only_fixture_comparison_ignores_translation_but_not_size():
    before = _snapshot((10, 20, 5))

    assert _fixture_equal(before, _snapshot((0, 0, 5)), "panel", geometry_only=True)
    assert not _fixture_equal(before, _snapshot((0, 0, 5), size=(35, 70, 10)), "panel", geometry_only=True)
    assert not _fixture_equal(before, _snapshot((0, 0, 5)), "panel")


def test_infrastructure_resume_uses_frozen_prompt_and_only_unfilled_slots():
    prompt = _frozen_v1_system_prompt(True)
    assert "【强制闭环" in prompt
    assert "【歧义门禁】" not in prompt
    assert _is_infrastructure_result({
        "task_id": "P2-HARD-024",
        "infrastructure_error": None,
        "runs": [{"error": {"code": "llm.connection"}}],
    })
    assert not _is_infrastructure_result({
        "task_id": "P2-HARD-028",
        "infrastructure_error": None,
        "runs": [{"error": {"code": "llm.connection"}}],
    })
