"""Public development views and durable controller accounting, without execution.

No loader, Rhino/SSH API, grant or private corpus access. A field entry must
independently verify owner authority, source/runtime and the fixed state root,
authenticate evidence and enforce deadlines before using this component.
Journal labels do not authenticate model/native receipts or prove cleanup.
"""
from __future__ import annotations

import hashlib
import fcntl
from functools import wraps
import os
from pathlib import Path
import stat

from plugin.rhino_listener.c5_research_channel import private_directory, publish_json, read_json
from plugin.rhino_listener.c5_research_native import digest, require
from training.lora_development_cases import build_cases
from training.lora_development_plan import development_schedule

STUDY = "lora-optimization-development-v1"
OUTCOMES = {"success", "task_failure", "engineering_failure", "evidence_unknown"}
STEP_OUTCOMES = {"completed_read", "completed_write", "abstained", "task_failure", "engineering_failure", "unknown"}


def _sha(value):
    require(type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value),
            "exact digest required")
    return value


def _exclusive(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        root = private_directory(self.root)
        try:
            fd = os.open("controller.lock", os.O_RDWR | os.O_NOFOLLOW, dir_fd=root)
        finally:
            os.close(root)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600, "private controller lock required")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            require(read_json(self.root, "lora-development-scope.json") == self.scope, "scope changed after open")
            return method(self, *args, **kwargs)
        finally:
            os.close(fd)  # Releases the lock, including on failure; never waits/retries.
    return locked


def field_views(plan):
    """Compile only public task/policy views, never scorer expectations."""
    schedule = development_schedule(plan)
    cases = {row["case"]["family_id"]: row for row in build_cases()}
    require([(row["id"], row["role"], row["template_family"]) for row in plan["families"]] == [
        (row["case"]["family_id"], row["role"], row["case"]["template_family"])
        for row in cases.values()], "public family definitions differ")
    model, native = {}, {}
    for cell in schedule:
        case = cases[cell["family_id"]]["case"]
        model[cell["slot_id"]] = {**cell, "task": case["task_text"], "max_steps": case["max_steps"]}
        native[cell["slot_id"]] = {**cell,
            "task_sha256": hashlib.sha256(case["task_text"].encode()).hexdigest(),
            "fixture_recipe": case["fixture_recipe"], "max_reads": case["max_reads"], "max_writes": 0}
    return {"schedule": schedule, "model": model, "native": native}


class DevelopmentJournal:
    """Append-only local accounting for a single frozen 32-cell development.

    Initialization only creates a CPU ledger. It never issues authority. The
    caller supplies audited outcomes/cleanup; neither booleans nor hashes are
    substitutes for native verification. Reopening requires the same root,
    plan and runtime. A different output folder cannot be admitted by the
    eventual field entry as a way to reset this ledger.
    """
    def __init__(self, state: Path, plan: dict, runtime_sha256: str, *, campaign=None, recovery=None,
                 compiled=None):
        self.limits = dict(plan['limits'])
        self.campaign = campaign
        self.recovery = recovery
        self.history = recovery['history'] if recovery is not None else {}
        self.root = Path(state)
        os.close(private_directory(self.root))
        if compiled is None:
            self.views, study = field_views(plan), STUDY
        else:
            from training.lora_comparison_plan import validate_compiled
            validate_compiled(plan, compiled)
            require(campaign is None and recovery is None, 'new study cannot inherit old execution grants')
            self.views, study = compiled['views'], compiled['study_id']
        self.selection_boundary = 16 if compiled is None else None
        self.common_chain = compiled is not None
        self.scope = {"study_id": study, "plan_sha256": digest(plan),
                      "runtime_sha256": _sha(runtime_sha256), "state_root": str(self.root)}
        if compiled is not None:
            self.scope['compiled_sha256'] = digest(compiled)
        if recovery is not None:
            require(set(recovery) == {'history', 'resolved_without_native_effect', 'review_sha256', 'incomplete_selection'}
                    and recovery['incomplete_selection'] == 'retain_original_without_candidate_promotion'
                    and set(recovery['resolved_without_native_effect']) == set(self.history), 'explicit reviewed continuation required')
            _sha(recovery['review_sha256'])
            schedule = self.views['schedule']
            require(list(self.history) == [c['slot_id'] for c in schedule[:len(self.history)]], 'history must be exact original prefix')
            for slot, row in self.history.items():
                cell = self._cell(slot)
                require(all(row['identity'][k] == cell[k] for k in ('slot_id', 'family_id', 'route', 'system', 'role'))
                        and row['identity']['study_id'] == STUDY, 'original slot identity differs')
            self.scope['continuation'] = recovery
        name = "lora-development-scope.json"
        if os.path.lexists(self.root / name):
            require(read_json(self.root, name) == self.scope, "development scope/root/runtime changed")
        else:
            require(not any(self.root.iterdir()), "new development ledger must be empty; no historical state reuse")
            publish_json(self.root, name, self.scope)
            publish_json(self.root, "controller.lock", {"scope_sha256": digest(self.scope)})
        require(read_json(self.root, "controller.lock") == {"scope_sha256": digest(self.scope)},
                "controller lock must exist from initialization; never recreate it")

    def _cell(self, slot):
        require(type(slot) is str and slot in self.views["model"], "slot outside fixed development scope")
        return self.views["model"][slot]

    def _identity(self, slot):
        if slot in self.history: return self.history[slot]['identity']
        cell = self._cell(slot)
        return {"study_id": self.scope['study_id'], "scope_sha256": digest(self.scope),
                **{k: cell[k] for k in ("slot_id", "family_id", "route", "system", "role")}}

    def slot_key(self, slot):
        return digest(self._identity(slot))

    def _read(self, slot, suffix):
        if slot in self.history:
            require(suffix == '.result.json', 'consumed history cannot be opened or replayed')
            return self.history[slot]
        return read_json(self.root, self.slot_key(slot) + suffix)

    def may_continue_after(self, slot, result):
        # This is a separate reviewed cleanup resolution, not a rewrite of
        # the old result's may_advance, effect_known or failed outcome.
        return (slot in self.history and slot in self.recovery['resolved_without_native_effect']) or result['may_advance'] is True

    def _write(self, slot, suffix, value):
        publish_json(self.root, self.slot_key(slot) + suffix, value)

    @_exclusive
    def start_slot(self, slot):
        require(slot not in self.history, 'consumed history cannot be replayed')
        identity = self._identity(slot)
        index = next(i for i, row in enumerate(self.views["schedule"]) if row["slot_id"] == slot)
        for prior in self.views["schedule"][:index]:
            result = self._read(prior["slot_id"], ".result.json")
            require(result["identity"] == self._identity(prior["slot_id"]) and self.may_continue_after(prior['slot_id'], result),
                    "earlier slot incomplete, uncertain or stopped")
        if identity["role"] == "acceptance":
            require(read_json(self.root, "selection.json") == self._selection(),
                    "selection must be fixed before acceptance")
        # O_EXCL publication prevents concurrent or reopened duplicate starts.
        if self.campaign is not None:
            self.campaign.claim_slot(slot)  # Global intent survives revision/root changes.
        self._write(slot, ".claim.json", {"identity": identity, "replay_allowed": False})
        return identity

    @_exclusive
    def start_step(self, slot, step_index):
        cell = self._cell(slot)
        require(type(step_index) is int and 0 <= step_index < cell["max_steps"], "step outside fixed policy")
        require(self._read(slot, ".claim.json")["identity"] == self._identity(slot), "slot not claimed")
        require(not os.path.lexists(self.root / (self.slot_key(slot) + ".result.json")), "slot already ended")
        for previous in range(step_index):
            require(self._read(slot, f".step-{previous}.result.json")["outcome"] in (
                {'completed_read', 'completed_write'} if self.common_chain else {'completed_read'}),
                    "predecessor incomplete or not a completed read")
        self._write(slot, f".step-{step_index}.claim.json", {"identity": self._identity(slot),
                    "step_index": step_index, "replay_allowed": False})

    @_exclusive
    def finish_step(self, slot, step_index, *, outcome, evidence_sha256):
        cell = self._cell(slot)
        require(type(step_index) is int and 0 <= step_index < cell["max_steps"], "invalid step index")
        require(not os.path.lexists(self.root / (self.slot_key(slot) + ".result.json")), "slot already ended")
        claimed = self._read(slot, f".step-{step_index}.claim.json")
        require(claimed["identity"] == self._identity(slot) and claimed["step_index"] == step_index,
                "step claim identity differs")
        require(outcome in STEP_OUTCOMES, "unknown step outcome")
        self._write(slot, f".step-{step_index}.result.json", {"outcome": outcome,
                    "evidence_sha256": _sha(evidence_sha256)})

    @_exclusive
    def finish_slot(self, slot, *, outcome, fixture_closed, listener_stopped, effect_known,
                    stop_requested, evidence_sha256, execution=None):
        require(outcome in OUTCOMES and all(type(value) is bool for value in
            (fixture_closed, listener_stopped, effect_known, stop_requested)), "explicit outcome and cleanup required")
        identity = self._identity(slot)
        require(self._read(slot, ".claim.json")["identity"] == identity, "slot not claimed")
        uncertain = []
        step_outcomes = []
        for index in range(self._cell(slot)["max_steps"]):
            stem = self.slot_key(slot) + f".step-{index}"
            if not os.path.lexists(self.root / (stem + ".claim.json")):
                continue
            if not os.path.lexists(self.root / (stem + ".result.json")):
                uncertain.append(index)
            else:
                status = self._read(slot, f".step-{index}.result.json")["outcome"]
                step_outcomes.append(status)
                if status in {"engineering_failure", "unknown"}:
                    uncertain.append(index)
        if uncertain or not (fixture_closed and listener_stopped and effect_known) or stop_requested:
            require(outcome in {"engineering_failure", "evidence_unknown"},
                    "uncertain work or cleanup cannot be classified as a quality outcome")
        if outcome == "task_failure":
            require(step_outcomes, "pre-model infrastructure failure is not a task failure")
        if outcome == "success":
            require(fixture_closed and listener_stopped and effect_known and not stop_requested
                    and step_outcomes and not uncertain and all(s in (
                        {'completed_read', 'completed_write', 'abstained'} if self.common_chain else
                        {'completed_read', 'abstained'}) for s in step_outcomes),
                    "success cannot hide incomplete/failed model work")
        result = {"identity": identity, "outcome": outcome, "fixture_closed": fixture_closed,
            "listener_stopped": listener_stopped, "effect_known": effect_known, "stop_requested": stop_requested,
            "uncertain_steps": uncertain, "evidence_sha256": _sha(evidence_sha256),
            "may_advance": bool(fixture_closed and listener_stopped and effect_known and not stop_requested
                                and not uncertain and outcome != "evidence_unknown")}
        if execution is not None:
            require(self.recovery is not None or self.common_chain,
                    'separate lifecycle fields require an explicit study contract')
            result['execution'] = execution
        self._write(slot, ".result.json", result)
        return result

    def _selection(self):
        cells = self.views["schedule"][:16]
        results = {cell["slot_id"]: self._read(cell["slot_id"], ".result.json") for cell in cells}
        require(all(results[c["slot_id"]]["identity"] == self._identity(c["slot_id"])
                    and self.may_continue_after(c['slot_id'], results[c['slot_id']]) for c in cells),
                "selection has unresolved/stopped or differently bound evidence")
        if self.recovery is not None and any(results[c['slot_id']]['outcome'] in {'engineering_failure', 'evidence_unknown'} for c in cells):
            return {'scope_sha256': digest(self.scope), 'selection_results_sha256': digest(results),
                    'selected_system': 'original', 'selection_complete': False, 'candidate_promoted': False,
                    'reason': 'incomplete_selection_retain_original', 'success_gains': None,
                    'development_selection_not_quality_claim': True}
        gains, new_engineering_failure = {}, False
        for route in ("base", "current_lora"):
            relevant = [cell for cell in cells if cell["route"] == route]
            counts = {system: sum(results[c["slot_id"]]["outcome"] == "success" for c in relevant
                                 if c["system"] == system) for system in ("original", "read_progress_v1")}
            gains[route] = counts["read_progress_v1"] - counts["original"]
            for family in {c["family_id"] for c in relevant}:
                paired = {c["system"]: results[c["slot_id"]]["outcome"] for c in relevant if c["family_id"] == family}
                new_engineering_failure |= (paired["read_progress_v1"] == "engineering_failure"
                                           and paired["original"] != "engineering_failure")
        candidate = sum(gains.values()) > 0 and min(gains.values()) >= 0 and not new_engineering_failure
        return {"scope_sha256": digest(self.scope), "selection_results_sha256": digest(results),
                "selected_system": "read_progress_v1" if candidate else "original", "success_gains": gains,
                "new_engineering_failure": new_engineering_failure, "development_selection_not_quality_claim": True}

    @_exclusive
    def seal_selection(self):
        decision = self._selection()
        publish_json(self.root, "selection.json", decision)
        return decision
