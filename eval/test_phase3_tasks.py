import json
import re
from collections import Counter
from pathlib import Path

from agent.collection_campaign import load_campaign, validate_campaign_tasks
from tools.generate_phase3_tasks import build_tasks, render_jsonl


ROOT = Path(__file__).resolve().parent.parent
TASK_FILE = ROOT / "eval" / "tasks" / "phase3_expansion.jsonl"
MANIFEST = ROOT / "eval" / "collection" / "phase3_300.json"


def test_phase3_generated_file_is_current_and_has_200_unique_tasks():
    generated = build_tasks()
    assert len(generated) == 200
    assert TASK_FILE.read_text(encoding="utf-8") == render_jsonl(generated)
    assert [task["id"] for task in generated] == [f"p3-{index:03d}" for index in range(1, 201)]
    assert len({task["instruction"] for task in generated}) == 200
    assert all(task["difficulty"] in {4, 5} for task in generated)


def test_phase3_campaign_reuses_100_and_adds_200_with_required_coverage():
    campaign = load_campaign(MANIFEST)
    assert campaign.target == 300
    assert len(campaign.tasks) == 300
    assert campaign.inherited_golden_campaign_ids == ["phase1-30", "phase2-100"]
    assert [task["id"] for task in campaign.tasks[-200:]] == [
        f"p3-{index:03d}" for index in range(1, 201)
    ]
    tags = Counter(tag for task in campaign.tasks for tag in task["tags"])
    assert len(tags) >= 40
    assert all(tags[tag] >= 10 for tag in ("boolean", "perception", "recovery", "group", "undo"))
    assert sum(task["difficulty"] >= 4 for task in campaign.tasks) >= 260


def test_phase3_instructions_are_not_numeric_only_duplicates():
    signatures = Counter(
        re.sub(r"\d+(?:\.\d+)?", "<N>", task["instruction"]).strip().lower()
        for task in build_tasks()
    )
    assert max(signatures.values()) <= 2


def test_phase3_manifest_validation_has_no_findings():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    campaign = load_campaign(MANIFEST)
    assert validate_campaign_tasks(
        campaign.tasks,
        target=campaign.target,
        requirements=manifest["diversity_requirements"],
    ) == []
