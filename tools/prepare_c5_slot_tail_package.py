#!/usr/bin/env python3
"""Preparation only. No approval writer, ledger activation or field actor."""
import argparse, copy, hashlib, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plugin.rhino_listener.c5_slot_protocol import (
    POLICY,
    validate_protocol,
    impact_indices,
)
from plugin.rhino_listener.c5_run_package_policy import (
    LAYOUT_FILE,
    validate_layout,
    validate_migration,
)
from plugin.rhino_listener.c5_research_native import digest, require

PACKAGE = "reuse-formal-20261024-r4"
SPEC = "eval/c5/" + PACKAGE + "-spec.json"
RUNTIME = "eval/c5/" + PACKAGE + "-runtime.json"
FACTS = "eval/c5/slot-tail-field-facts-20261024.json"
HISTORY = "eval/c5/slot-tail-original-public-history-20261024.json"
WORK = "eval/c5/slot-tail-work-plan-20261024.json"
REVIEW = "eval/c5/slot-tail-package-review-20261024.json"
LAYOUT = "eval/c5/slot-tail-package-layout-20261024.json"


def read(name):
    return json.loads((ROOT / name).read_bytes())


def encoded(v):
    return (
        json.dumps(
            v,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()


def assemble():
    s = copy.deepcopy(read("eval/c5/reuse-formal-20261023-r3-spec.json"))
    f = copy.deepcopy(read("eval/c5/reuse-formal-20261023-r3-runtime.json"))
    facts = read(FACTS)
    history = read(HISTORY)
    layout = {
        "schema_version": 1,
        "package_id": PACKAGE,
        "study_id": POLICY["study_id"],
        "mac_source_root": "/Users/xiongweiluo/RhinoCoder/data/training/c5/"
        + PACKAGE
        + "-source",
        "gpu_source_root": "/data/" + PACKAGE + "-source",
        "mac_state_root": "/Users/xiongweiluo/RhinoCoder/data/training/c5/"
        + PACKAGE
        + "-state",
        "gpu_state_root": "/data/" + PACKAGE + "-state",
        "spec_file": SPEC,
        "runtime_file": RUNTIME,
        "policy_sha256": digest(POLICY),
    }
    validate_layout(layout)
    from training.c5_formal_reuse_admission import formal_replay

    observed = formal_replay(
        f["incremental_revision"]["initial_campaign_scope"],
        history["prior_campaign_events"],
    )
    global_indices = list(observed.get("slot_global_attempted_indices", range(7)))
    plan = {
        "version": 1,
        "kind": "interrupted_continuation",
        "selected_indices": list(range(len(global_indices), 40)),
        "prior_attempted_indices": global_indices,
        "prior_audit_sha256": digest(
            read("eval/c5/slot-attempt4-owner-raw-review-result-20261024.json")
        ),
        "prior_settlement_sha256": digest(
            read("eval/c5/slot-attempt4-original-gpu-settlement-20261024.json")
        ),
        "prior_ledger_head_sha256": history["prior_campaign_head_sha256"],
        "code_change_scope": "shared_logic",
        "regression_wave": 0,
        "original_result_immutable": True,
    }
    work = read(WORK)
    require(
        set(work) == {"kind", "affected_indices", "change_scope"}
        and work["kind"] in ("interrupted_continuation", "engineering_regression"),
        "slot_explicit_work_plan",
    )
    if work["kind"] == "engineering_regression":
        plan.update(
            kind="engineering_regression",
            selected_indices=impact_indices(
                work["affected_indices"], work["change_scope"]
            ),
            code_change_scope=work["change_scope"],
            regression_wave=1,
        )
    else:
        require(
            work["affected_indices"] == [] and work["change_scope"] == "shared_logic",
            "slot_continuation_not_failed_slot_rerun",
        )
    validate_protocol(plan)
    package = s["run_package"]
    package.update(
        policy=POLICY,
        layout=layout,
        slot_protocol=plan,
        prior_campaign_events=history["prior_campaign_events"],
        previous_mac_source_root="/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-formal-20261023-r3-source",
        previous_gpu_source_root="/data/reuse-formal-20261023-r3-source",
        previous_public_source_files=history["original_source_files"],
        original_private_attempt_root="/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-formal-20261023-r2-state/preload-3",
        original_audit_root="/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-formal-20261023-r2-partial-audit-v2-state",
        original_settlement_root="/Users/xiongweiluo/RhinoCoder/data/training/c5",
        original_settlement_name="slot-attempt4-original-gpu-settlement-20261024.json",
    )
    from plugin.rhino_listener.c5_slot_tail_policy import POLICY as TAIL_POLICY
    package['tail_repair']={'version':1,'policy':TAIL_POLICY,
        'prior_review':history['tail_review_reference']}
    package.pop("previous_release_observation_file_sha256", None)
    migration = package["timing_migration"]
    migration.update(
        prior_campaign_head_sha256=history["prior_campaign_head_sha256"],
        prior_attempts_consumed=history["prior_attempts_consumed"],
        legacy_elapsed_debit_seconds=history["gpu_charged_seconds"],
        gpu_residency_upper_seconds=history["gpu_charged_seconds"],
    )
    validate_migration(migration, attempts_max=POLICY["global_loads_max"])
    code = facts.get("source_code_revision")
    blockers = [
        k
        for k in (
            "original_exit_audit_settlement_closed",
            "mac_cpu_closure",
            "linux_cpu_closure",
            "latest_gpu_identity_idle",
            "prior_frozen_sources_unchanged",
            "both_public_deployments",
            "independent_public_readback",
        )
        if facts.get(k) is not True
    ]
    s.update(
        instance_id=PACKAGE,
        run_package=package,
        execution_ready=not blockers,
        state=(
            "slot_rules_material_review_pending_separate_execution_approval"
            if not blockers
            else "disabled_slot_rules_preparation"
        ),
        deployment_revision=code,
        mac_source_root=layout["mac_source_root"],
        remote_source_root=layout["gpu_source_root"],
        mac_state_root=layout["mac_state_root"],
        remote_state_root=layout["gpu_state_root"],
        next_preexposure_attempt=None,
        formal_gpu_seconds_max=POLICY["gpu_residency_seconds_max"],
    )
    s["observer_backend"]["code_read_roots"] = [
        (
            layout["mac_source_root"]
            if x.startswith("/Users/xiongweiluo/RhinoCoder/data/training/c5/")
            else x
        )
        for x in s["observer_backend"]["code_read_roots"]
    ]
    s["entry_return_wrapper"] = (
        "#! python 3\nimport runpy\nrunpy.run_path("
        + repr(layout["mac_source_root"] + "/tools/c5_rhino_run_package.py")
        + ', run_name="__main__")\n'
    )
    s["entry_return_wrapper_template"] = s["entry_return_wrapper"]
    docs = {SPEC: s, LAYOUT_FILE: layout}
    source = set(f["source_files"]) | {
        SPEC,
        LAYOUT_FILE,
        FACTS,
        HISTORY,
        WORK,
        "eval/c5/reuse-formal-20261023-r3-runtime.json",
        "eval/c5/slot-protocol-package-layout-20261023.json",
        "eval/c5/slot-attempt4-late-native-cleanup-20261024.json",
        "eval/c5/slot-attempt4-owner-raw-review-result-20261024.json",
        "eval/c5/slot-attempt4-original-gpu-settlement-20261024.json",
    }
    source |= {
        p.relative_to(ROOT).as_posix()
        for folder in ("training", "tools", "plugin/rhino_listener")
        for p in (ROOT / folder).glob("*.py")
        if any(x in p.name for x in ("slot_", "formal_reuse_partial"))
    }
    for n in sorted(source):
        if n.endswith(".py"):
            result = subprocess.run(
                ["git", "show", str(code) + ":" + n], cwd=ROOT, capture_output=True
            )
            if result.returncode or result.stdout != (ROOT / n).read_bytes():
                blockers.append("exact_source_code_commit")
                break
    ready = not blockers
    s.update(
        execution_ready=ready,
        state=(
            "slot_rules_material_review_pending_separate_execution_approval"
            if ready
            else "disabled_slot_rules_preparation"
        ),
    )
    pins = {
        n: hashlib.sha256(
            encoded(docs[n]) if n in docs else (ROOT / n).read_bytes()
        ).hexdigest()
        for n in sorted(source)
    }
    f.update(
        instance_id=PACKAGE,
        run_package=package,
        execution_ready=ready,
        spec_sha256=digest(s),
        spec_file_sha256=pins[SPEC],
        source_files=pins,
        source_inventory_sha256=digest(pins),
        source_revision=code,
        mac_source_root=layout["mac_source_root"],
        remote_source_root=layout["gpu_source_root"],
    )
    if facts.get("mac_environment"):
        f["mac_environment"] = facts["mac_environment"]
    if facts.get("environment"):
        f["environment"] = facts["environment"]
        f["environment_sha256"] = digest(f["environment"])
    f["field_plan"]["instance_id"] = PACKAGE
    f["fixed_public_files"] = {
        n: pins[n]
        for n in set(f["fixed_public_files"])
        | {
            SPEC,
            LAYOUT_FILE,
            FACTS,
            HISTORY,
            WORK,
            "eval/c5/slot-attempt4-owner-raw-review-result-20261024.json",
            "eval/c5/slot-attempt4-original-gpu-settlement-20261024.json",
        }
    }
    from training.c5_formal_reuse_control import code_closure

    f["control_source_files"] = code_closure(
        ROOT, "tools/c5_formal_reuse_control.py", pins
    )
    f.update(
        current_gpu_full_bytes_verified=not blockers,
        current_mac_full_bytes_verified=not blockers,
        actual_public_deployment_both_endpoints_verified=not blockers,
    )
    docs[RUNTIME] = f
    docs[REVIEW] = {
        "schema_version": 1,
        "package_id": PACKAGE,
        "study_id": s["study_id"],
        "status": (
            "COMPLETE_MATERIAL_REVIEW_PENDING_SEPARATE_EXECUTION_APPROVAL"
            if ready
            else "DISABLED_PREPARATION"
        ),
        "spec_sha256": digest(s),
        "runtime_sha256": digest(f),
        "source_code_revision": code,
        "source_inventory_sha256": digest(pins),
        "public_source_files": len(pins),
        "blockers": sorted(set(blockers)),
        "actual_execution_authorized": False,
        "new_grant_or_ledger_event_created": False,
        "first_result_unchanged": True,
        "attempts_preserved": history["prior_attempts_consumed"],
        "first_load_epoch_preserved": history["first_load_epoch"],
        "charged_gpu_seconds_preserved": history["gpu_charged_seconds"],
        "continuation_indices_count": (
            len(plan["selected_indices"])
            if plan["kind"] == "interrupted_continuation"
            else 0
        ),
        "regression_targets_authorized_by_this_package": (
            plan["selected_indices"] if plan["kind"] == "engineering_regression" else []
        ),
        "rules": POLICY,
        "remaining_work_estimate_seconds": len(plan["selected_indices"])
        * POLICY["slot_work_upper_seconds"],
        "startup_plus_export_seconds": 1500,
        "estimate_is_worst_case_completion_guarantee": False,
        "historical_phase_gate_passed": False,
        "historical_refusals_retained": True,
        "tail_repair_policy": package['tail_repair']['policy'],
        "effective_new_loads_remaining": POLICY['global_loads_max']-history['prior_attempts_consumed'],
        "formal_residency_seconds_remaining": 129600 - history["gpu_charged_seconds"],
        "private_content_included": False,
    }
    return docs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    a = p.parse_args()
    docs = assemble()
    for name, v in docs.items():
        path = ROOT / (LAYOUT if name == LAYOUT_FILE else name)
        raw = encoded(v)
        if a.check:
            require(path.read_bytes() == raw, "slot_saved_candidate_drift:" + name)
        else:
            path.write_bytes(raw)
    print(json.dumps(docs[REVIEW], sort_keys=True))


if __name__ == "__main__":
    main()
