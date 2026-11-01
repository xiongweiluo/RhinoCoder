"""Public CPU accounting checks. No native host, generator, grant or old state."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from plugin.rhino_listener.c5_research_native import NativeError
from training.lora_development_scope import DevelopmentJournal, field_views

PLAN = Path(__file__).resolve().parents[1] / "eval/lora-development/proposed-development-plan.json"
RUNTIME = "a" * 64
EVIDENCE = "b" * 64  # Explicit synthetic evidence, never a real audit.


@pytest.fixture
def plan():
    return json.loads(PLAN.read_text())


@pytest.fixture
def ledger(tmp_path, plan):
    root = tmp_path / "new-development"
    root.mkdir(mode=0o700)
    return DevelopmentJournal(root, plan, RUNTIME)


def finish(ledger, slot, outcome="success", **changes):
    fields = dict(outcome=outcome, fixture_closed=True, listener_stopped=True,
                  effect_known=True, stop_requested=False, evidence_sha256=EVIDENCE)
    fields.update(changes)
    return ledger.finish_slot(slot, **fields)


def complete(ledger, slot, outcome="success"):
    ledger.start_slot(slot)
    if outcome != "engineering_failure":
        ledger.start_step(slot, 0)
        ledger.finish_step(slot, 0, outcome="abstained" if outcome == "success" else "task_failure",
                           evidence_sha256=EVIDENCE)
    return finish(ledger, slot, outcome)


def test_field_views_separate_model_input_from_fixture_and_scoring(plan):
    views = field_views(plan)
    assert len(views["model"]) == len(views["native"]) == 32
    assert "expected_operations" not in json.dumps(views)
    assert "assertions" not in json.dumps(views)
    for row in views["model"].values():
        assert set(row) == {"slot_id", "role", "family_id", "route", "system", "task", "max_steps"}
        assert "fixture_recipe" not in row
    for row in views["native"].values():
        assert row["max_writes"] == 0 and row["max_reads"] <= 2
        assert len(row["fixture_recipe"]) == 7
    altered = copy.deepcopy(plan)
    altered["families"][0]["id"] = "unregistered-public-task"
    with pytest.raises(NativeError):
        field_views(altered)


def test_all_32_system_route_cells_have_distinct_claims(ledger):
    assert len({ledger.slot_key(c["slot_id"]) for c in ledger.views["schedule"]}) == 32
    # Original and candidate can each run once for the same family/weight.
    for cell in ledger.views["schedule"][:4]:
        complete(ledger, cell["slot_id"])
    assert len(list(ledger.root.glob("*.claim.json"))) == 8  # slot + step


def test_concurrent_or_reopened_claim_cannot_repeat_a_slot(ledger, plan):
    def claim():
        try:
            ledger.start_slot("lora-dev-00")
            return True
        except (FileExistsError, BlockingIOError):
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: claim(), range(2))) == [False, True]
    reopened = DevelopmentJournal(ledger.root, plan, RUNTIME)
    with pytest.raises(FileExistsError):
        reopened.start_slot("lora-dev-00")
    with pytest.raises(FileNotFoundError):
        reopened.start_slot("lora-dev-01")
    with pytest.raises(NativeError):
        DevelopmentJournal(ledger.root, plan, "c" * 64)
    altered = copy.deepcopy(plan)
    altered["limits"]["slot_seconds"] -= 1
    with pytest.raises(NativeError):
        DevelopmentJournal(ledger.root, altered, RUNTIME)


def test_no_historical_directory_adoption(tmp_path, plan):
    tmp_path.chmod(0o700)
    old = tmp_path / "historical-consumption.json"
    old.write_text("preserve")
    with pytest.raises(NativeError):
        DevelopmentJournal(tmp_path, plan, RUNTIME)
    assert old.read_text() == "preserve"
    assert len(list(tmp_path.iterdir())) == 1


def test_interruption_after_claim_stays_uncertain_and_cannot_replay(ledger, plan):
    slot = "lora-dev-00"
    ledger.start_slot(slot)
    ledger.start_step(slot, 0)
    reopened = DevelopmentJournal(ledger.root, plan, RUNTIME)
    with pytest.raises(FileExistsError):
        reopened.start_step(slot, 0)
    with pytest.raises(FileNotFoundError):
        reopened.start_step(slot, 1)
    with pytest.raises(NativeError):
        finish(reopened, slot)
    result = finish(reopened, slot, "engineering_failure")
    assert result["uncertain_steps"] == [0] and not result["may_advance"]
    with pytest.raises(NativeError):
        reopened.start_slot("lora-dev-01")
    with pytest.raises(NativeError):
        reopened.finish_step(slot, 0, outcome="completed_read", evidence_sha256=EVIDENCE)


@pytest.mark.parametrize("fault", ["fixture_closed", "listener_stopped", "effect_known", "stop_requested"])
def test_unverified_cleanup_effect_or_owner_stop_blocks_next_cell(ledger, fault):
    ledger.start_slot("lora-dev-00")
    result = finish(ledger, "lora-dev-00", "engineering_failure", **{fault: fault == "stop_requested"})
    assert not result["may_advance"]
    with pytest.raises(NativeError):
        ledger.start_slot("lora-dev-01")


def test_task_failure_is_retained_without_retry_and_clean_next_cell_can_proceed(ledger):
    result = complete(ledger, "lora-dev-00", "task_failure")
    assert result["may_advance"] and result["outcome"] == "task_failure"
    with pytest.raises(FileExistsError):
        ledger.start_slot("lora-dev-00")
    ledger.start_slot("lora-dev-01")


def test_only_completed_read_permits_second_step(ledger):
    ledger.start_slot("lora-dev-00")
    ledger.start_step("lora-dev-00", 0)
    ledger.finish_step("lora-dev-00", 0, outcome="abstained", evidence_sha256=EVIDENCE)
    with pytest.raises(NativeError):
        ledger.start_step("lora-dev-00", 1)
    assert len(list(ledger.root.glob("*.step-1.claim.json"))) == 0


def test_second_step_and_full_population_keep_selection_fixed_despite_acceptance_failures(ledger):
    for cell in ledger.views["schedule"][:16]:
        slot = cell["slot_id"]
        ledger.start_slot(slot)
        for step in range(ledger.views["model"][slot]["max_steps"]):
            ledger.start_step(slot, step)
            ledger.finish_step(slot, step, outcome="completed_read", evidence_sha256=EVIDENCE)
        finish(ledger, slot)
    decision = ledger.seal_selection()
    for cell in ledger.views["schedule"][16:]:
        complete(ledger, cell["slot_id"], "task_failure")
    assert len(list(ledger.root.glob("*.result.json"))) == 72  # 32 slots + 40 steps
    assert json.loads((ledger.root / "selection.json").read_text()) == decision
    with pytest.raises(FileExistsError):
        ledger.start_slot("lora-dev-31")
    with pytest.raises(NativeError):
        ledger.start_slot("lora-dev-32")


@pytest.mark.parametrize("mode,expected", [
    ("gain", "read_progress_v1"), ("tie", "original"),
    ("regress_one_weight", "original"), ("new_engineering_failure", "original")])
def test_selection_is_derived_once_before_acceptance_and_cannot_be_revised(ledger, mode, expected):
    with pytest.raises(FileNotFoundError):
        ledger.seal_selection()
    for cell in ledger.views["schedule"][:16]:
        candidate = cell["system"] == "read_progress_v1"
        outcome = "success" if candidate or mode == "tie" else "task_failure"
        if mode == "regress_one_weight" and cell["route"] == "base":
            outcome = "task_failure" if candidate else "success"
        if mode == "new_engineering_failure" and candidate and cell["family_id"] == "DEV-S01":
            outcome = "engineering_failure"
        complete(ledger, cell["slot_id"], outcome)
    with pytest.raises(FileNotFoundError):
        ledger.start_slot("lora-dev-16")
    decision = ledger.seal_selection()
    assert decision["selected_system"] == expected
    assert decision["development_selection_not_quality_claim"]
    ledger.start_slot("lora-dev-16")
    with pytest.raises(FileExistsError):
        ledger.seal_selection()
    assert json.loads((ledger.root / "selection.json").read_text()) == decision
