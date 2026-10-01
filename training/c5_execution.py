"""C5-only bounded QLoRA execution. No holdout loader or Rhino executor.

The immutable CPU config remains unchanged. A separate owner authorization
binds its hash, the execution code, and conditional stage budgets. Resume is
only from verified checkpoints of the same run, in an independent process.
"""
from __future__ import annotations

import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
import random
import shutil
import signal
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from training.c5_contract import (
    BASE_MODEL_REVISION, CONTRACT_ID, CORE_INVOCATION_TOOLS, DECODE_CONFIG,
    EXPERIMENT_ID, parse_invocation, parse_selection, render_invocation,
    render_selection,
)
from training.c5_engineering import (
    C5CausalLMCollator, C5EngineeringError, C5TokenizedDataset, load_config,
    load_pinned_tokenizer, render_development_records, select_overfit_smoke,
    verify_development_splits,
)
from training.c5_freeze import canonical_bytes, sha256_file
from training.tool_contract_candidate import ContractError
from training.c5_inventory import load_public_mcp_tools

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_FILES = ("training/c5_execution.py", "tools/run_c5_gpu.py", "training/c5_engineering.py", "training/c5_inventory.py")
PHASE_CAPS = {"overfit": 128, "system": 26, "formal": 132}


class ExecutionError(C5EngineeringError):
    pass


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExecutionError("JSON root must be an object")
    return value


def write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n"); f.flush(); os.fsync(f.fileno())
    else:
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)


def append_event(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(canonical_bytes(value).decode() + "\n")
        f.flush(); os.fsync(f.fileno())


def execution_hashes() -> dict[str, str]:
    return {name: sha256_file(ROOT / name) for name in EXECUTION_FILES}


def verify_authorization(path: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    a = read_json(path)
    if (a.get("experiment_id") != EXPERIMENT_ID
        or a.get("contract_id") != CONTRACT_ID
        or a.get("authorized_by") != "repository_owner"
        or a.get("engineering_config_sha256") != digest(config)
        or a.get("execution_sha256") != execution_hashes()
        or a.get("diagnostic_gpu_hours_max") != 4
        or a.get("formal_gpu_hours_max") != 8
        or a.get("final_gpu_hours_max") != 4
        or a.get("total_gpu_hours_max") != 16
        or a.get("diagnostic_runs_max") != 2
        or a.get("lease_remaining_hours_reported") != 48
        or a.get("new_rental_allowed") is not False
        or a.get("holdout_access_during_training") is not False
        or a.get("formal_requires_engineering_pass") is not True
        or a.get("conditional_formal_execution_authorized") is not True
        or not isinstance(a.get("execution_deadline_epoch"), (int, float))):
        raise ExecutionError("owner authorization, execution hash or budget drift")
    return a


def verify_snapshot(snapshot: Path, manifest: Path) -> dict[str, Any]:
    m = read_json(manifest)
    root = Path(m["approved_root"]).resolve(strict=True)
    if snapshot.resolve() != Path(m["snapshot_dir"]).resolve() or snapshot.name != BASE_MODEL_REVISION:
        raise ExecutionError("base snapshot revision or path drift")
    if len(m["file_sha256"]) != 14:
        raise ExecutionError("complete base snapshot manifest required")
    for name, expected in m["file_sha256"].items():
        p = snapshot / name
        if not p.resolve(strict=True).is_relative_to(root) or sha256_file(p) != expected:
            raise ExecutionError("base snapshot file hash or boundary drift: " + name)
    return {"revision": BASE_MODEL_REVISION, "manifest_sha256": sha256_file(manifest), "files": 14}


def checkpoint_manifest(path: Path, context_hash: str) -> dict[str, Any]:
    files = {p.relative_to(path).as_posix(): sha256_file(p)
             for p in sorted(path.rglob("*")) if p.is_file() and p.name != "lineage.json"}
    return {"context_sha256": context_hash, "files": files}


def verify_checkpoint(path: Path, context_hash: str) -> dict[str, Any]:
    stored = read_json(path / "lineage.json")
    if stored != checkpoint_manifest(path, context_hash):
        raise ExecutionError("checkpoint lineage or bytes changed")
    if not {"adapter_model.safetensors", "adapter_config.json", "state.pt", "progress.json"}.issubset(stored["files"]):
        raise ExecutionError("incomplete checkpoint")
    return read_json(path / "progress.json")


def selection_key(metrics: Mapping[str, Any]) -> tuple[float, float, float, float]:
    return (float(metrics["sequence_exact"]), float(metrics["arguments_exact"]),
            float(metrics["parse_exact"]), -float(metrics["eval_loss"]))


def finite(value: Any, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ExecutionError("non-finite " + label)
    return value


def choose_records(records: Sequence[Any], phase: str) -> list[Any]:
    if phase == "overfit":
        return select_overfit_smoke(records)
    train = [r for r in records if r.split == "train"]
    if phase == "system":
        families = sorted({r.family_id for r in train},
                          key=lambda f: hashlib.sha256(("c5-system-v1:" + f).encode()).hexdigest())[:32]
        train = [r for r in train if r.family_id in families]
    if phase not in PHASE_CAPS:
        raise ExecutionError("unknown phase")
    return train


def generation(model: Any, tokenizer: Any, prompt: str, stage: str) -> dict[str, Any]:
    import torch
    encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
    encoded = {k: v.to(model.device) for k, v in encoded.items()}
    reserve = DECODE_CONFIG[stage + "_max_new_tokens"]
    if encoded["input_ids"].shape[1] + reserve > 2048:
        raise ExecutionError("generation would exceed frozen context budget")
    started = time.monotonic()
    with torch.no_grad():
        output = model.generate(**encoded, do_sample=False, num_beams=1,
                                max_new_tokens=reserve, use_cache=True,
                                pad_token_id=tokenizer.pad_token_id,
                                eos_token_id=tokenizer.eos_token_id)
    continuation = output[0, encoded["input_ids"].shape[1]:]
    raw = tokenizer.decode(continuation, skip_special_tokens=False)
    return {"raw": raw, "tokens": len(continuation), "seconds": time.monotonic() - started,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "output_sha256": hashlib.sha256(raw.encode()).hexdigest()}


def score_family(family: Mapping[str, Any], generate: Any, tokenizer: Any,
                 tools: Sequence[Any]) -> dict[str, Any]:
    """End-to-end selector -> its selected single schema. Never oracle-force a tool.

    Family metrics require every expected step, not an average over records.
    Stateless multistep evaluation uses supplied per-step scene text; actual
    geometry/state transition validation belongs exclusively to C5-6.
    """
    flags = {k: True for k in ("parse_exact", "tool_name_exact", "arguments_exact", "sequence_exact")}
    selected: dict[str, Any] = {}
    receipts = []
    outcomes = []
    safety = False
    for record in family["records"]:
        stage = record["stage"]; step = record["user_step"]
        expected = record.get("selected_tool")
        result = None
        try:
            if stage == "selector":
                prompt = render_selection(tokenizer, step, tools).prompt
                result = generate(prompt, "selector")
                parsed = parse_selection(result["raw"], tools)
                selected[step] = parsed
                name_ok = parsed == expected
                args_ok = name_ok
                outcomes.append(name_ok)
                if (family.get("category") == "refusal" or family.get("holdout_stratum") == "refusal_or_no_tool") and parsed is not None:
                    safety = True
            else:
                actual = selected.get(step)
                if actual not in CORE_INVOCATION_TOOLS:
                    raise ContractError("no selected core tool for required invocation")
                prompt = render_invocation(tokenizer, step, tools, actual).prompt
                result = generate(prompt, "invocation")
                parsed = parse_invocation(result["raw"], actual, tools)
                name_ok = actual == expected
                args_ok = name_ok and parsed["arguments"] == record.get("arguments")
            receipts.append({"record_id": record["record_id"], "stage": stage,
                             "prompt_sha256": result["prompt_sha256"],
                             "output_sha256": result["output_sha256"],
                             "output_tokens": result["tokens"], "seconds": result["seconds"],
                             "parsed": True, "name_exact": name_ok, "arguments_exact": args_ok})
            flags["tool_name_exact"] &= name_ok
            flags["arguments_exact"] &= args_ok
            flags["sequence_exact"] &= name_ok and args_ok
        except ContractError:
            flags = {k: False for k in flags}
            # Preserve earlier successful receipts, and fail closed without repair.
            receipt = {"record_id": record["record_id"], "stage": stage, "parsed": False}
            if result is not None:
                receipt.update(prompt_sha256=result["prompt_sha256"], output_sha256=result["output_sha256"],
                               output_tokens=result["tokens"], seconds=result["seconds"])
            receipts.append(receipt)
            outcomes.append(False)
    return {"family_id": family["family_id"], **flags,
            "category": family.get("holdout_stratum", family.get("category")),
            "outcome_correct": bool(outcomes) and all(outcomes),
            "critical_safety_error": safety, "receipts": receipts,
            "contract_id": CONTRACT_ID, "repair_count": 0, "dispatch_count": 0}


def evaluate_families(model: Any, tokenizer: Any, families: Sequence[Any],
                      check_deadline: Any = lambda: None) -> tuple[dict[str, float], list[Any]]:
    model.eval()
    tools = load_public_mcp_tools()
    rows = []
    for family in families:
        check_deadline()
        rows.append(score_family(family, lambda prompt, stage: generation(model, tokenizer, prompt, stage),
                                 tokenizer, tools))
    return ({k: sum(r[k] for r in rows) / len(rows)
             for k in ("parse_exact", "tool_name_exact", "arguments_exact", "sequence_exact")}, rows)


def execute(args: Any) -> dict[str, Any]:
    import torch
    import bitsandbytes as bnb
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig, get_cosine_schedule_with_warmup

    config = load_config()
    authorization = verify_authorization(args.authorization, config)
    if args.phase not in PHASE_CAPS:
        raise ExecutionError("unknown phase")
    root = args.run_root.resolve()
    if any(x in str(root).lower() for x in ("holdout", "/a5/", "/p2/")):
        raise ExecutionError("protected run path")
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / "execution.lock").open("a+")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    phase = args.phase
    run = root / phase
    if args.resume_step is None and run.exists():
        raise ExecutionError("run already exists; no silent rerun or overwrite")
    if phase == "system" and read_json(root / "overfit" / "result.json").get("passed") is not True:
        raise ExecutionError("overfit gate has not passed")
    if phase == "formal" and any(read_json(root / p / "result.json").get("passed") is not True
                                 for p in ("overfit", "system")):
        raise ExecutionError("engineering gate has not passed")
    if phase == "formal" and (root / "formal" / "registry.json").exists():
        raise ExecutionError("formal adapter already registered")
    for prior_phase in (() if phase == "overfit" else ("overfit",) if phase == "system" else ("overfit", "system")):
        prior_context = read_json(root / prior_phase / "context.json")
        prior_result = read_json(root / prior_phase / "result.json")
        if (prior_context["execution_sha256"] != execution_hashes()
            or prior_context["authorization_sha256"] != digest(authorization)
            or prior_result["context_sha256"] != digest(prior_context)):
            raise ExecutionError("prior engineering gate lineage drift")
    events_path = root / "execution-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
    starts = [e for e in events if e["event"] == "start"]
    finishes = {e["segment_id"]: e for e in events if e["event"] == "finish"}
    if any(e["segment_id"] not in finishes for e in starts):
        raise ExecutionError("unsettled prior segment requires operator audit; no unaccounted resume")
    if args.resume_step is None and phase != "formal" and sum(e.get("new_run", False) and e["phase"] != "formal" for e in starts) >= 2:
        raise ExecutionError("two diagnostic runs exhausted")
    used = sum(e["seconds"] for e in finishes.values())
    diag_used = sum(e["seconds"] for e in finishes.values() if e["phase"] != "formal")
    formal_used = sum(e["seconds"] for e in finishes.values() if e["phase"] == "formal")
    stage_remaining = (8 * 3600 - formal_used) if phase == "formal" else (4 * 3600 - diag_used)
    limit = min(stage_remaining, 16 * 3600 - used, float(authorization["execution_deadline_epoch"]) - time.time() - 900)
    if limit <= 0:
        raise ExecutionError("budget or conservative lease deadline exhausted")
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise ExecutionError("CUDA/BF16 unavailable")
    if torch.cuda.get_device_properties(0).total_memory < 16 * 1024**3:
        raise ExecutionError("less than 16 GiB GPU memory")
    snapshot_info = verify_snapshot(args.snapshot, args.snapshot_manifest)
    families = verify_development_splits(args.dataset_dir, config=config)
    tokenizer = load_pinned_tokenizer(args.snapshot, config=config)
    records = render_development_records(families, tokenizer)
    readiness = read_json(ROOT / "eval/c5/c5-engineering-readiness.json")
    spec = read_json(ROOT / "eval/c5/offline-freeze-spec.json")
    if digest(load_public_mcp_tools()) != readiness["public_tool_schema_sha256"]:
        raise ExecutionError("runtime tool schema differs from CPU freeze")
    for filename, expected in spec["contract"]["implementation_sha256"].items():
        if sha256_file(ROOT / filename) != expected:
            raise ExecutionError("frozen contract implementation changed: " + filename)
    lineage_payload = [{"record_id": r.record_id, "split": r.split, "stage": r.stage,
        "prompt_sha256": hashlib.sha256(r.prompt.encode()).hexdigest(),
        "target_sha256": hashlib.sha256(r.target.encode()).hexdigest(), "full_tokens": r.full_tokens}
        for r in records]
    if digest(lineage_payload) != readiness["rendered_lineage_sha256"]:
        raise ExecutionError("rendered prompts/targets differ from original CPU freeze")
    chosen = choose_records(records, phase)
    smoke_hash = digest([r.record_id for r in select_overfit_smoke(records)])
    if smoke_hash != read_json(ROOT / "eval/c5/c5-engineering-readiness.json")["overfit_smoke"]["record_ids_sha256"]:
        raise ExecutionError("frozen smoke ID drift")
    steps_per_epoch = math.ceil(len(chosen) / 16)
    total_steps = PHASE_CAPS[phase] if phase != "formal" else steps_per_epoch * 3
    if phase == "formal" and total_steps != 132:
        raise ExecutionError("unexpected formal step count")
    context = {"experiment_id": EXPERIMENT_ID, "contract_id": CONTRACT_ID, "phase": phase,
               "config_sha256": digest(config), "authorization_sha256": digest(authorization),
               "execution_sha256": execution_hashes(), "snapshot": snapshot_info,
               "cpu_report_sha256": sha256_file(ROOT / "eval/c5/c5-engineering-readiness.json"),
               "dataset_manifest_sha256": sha256_file(ROOT / "eval/c5/dataset-v2-freeze-manifest.json"),
               "source_revision": (ROOT / "SOURCE_REVISION").read_text().strip(),
               "record_ids_sha256": digest([r.record_id for r in chosen]),
               "total_steps": total_steps, "steps_per_epoch": steps_per_epoch,
               "final_holdout_rows_read": 0}
    context_hash = digest(context)
    run.mkdir(exist_ok=True)
    if args.resume_step is None:
        write_json(run / "context.json", context, exclusive=True)
    elif read_json(run / "context.json") != context:
        raise ExecutionError("resume context drift")
    start = time.monotonic(); start_epoch = time.time()
    segment = f"{phase}-{time.time_ns()}"
    append_event(events_path, {"event": "start", "phase": phase, "segment_id": segment,
                              "new_run": args.resume_step is None, "start_epoch": start_epoch,
                              "context_sha256": context_hash})
    def stop_handler(_signum, _frame):
        raise ExecutionError("budget stop or operator interrupt")
    old_alarm = signal.signal(signal.SIGALRM, stop_handler)
    old_term = signal.signal(signal.SIGTERM, stop_handler)
    signal.setitimer(signal.ITIMER_REAL, limit)
    def check_deadline():
        if time.monotonic() - start >= limit:
            raise ExecutionError("GPU budget exhausted")
    result: dict[str, Any] = {}
    try:
        random.seed(20260928); torch.manual_seed(20260928); torch.cuda.manual_seed_all(20260928)
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.cuda.reset_peak_memory_stats()
        packages = {n: importlib.metadata.version(n) for n in
                    ("torch", "transformers", "peft", "accelerate", "bitsandbytes", "safetensors")}
        for line in (ROOT / "requirements-training.txt").read_text().splitlines():
            if "==" in line and not line.startswith("#"):
                name, version = line.split("==")
                if packages.get(name, "").split("+")[0] != version:
                    raise ExecutionError("locked training dependency drift: " + name)
        write_json(run / ("environment-" + segment + ".json"), {"packages": packages,
            "torch_cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
            "python": os.sys.version, "segment": segment})
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
        model = AutoModelForCausalLM.from_pretrained(args.snapshot, local_files_only=True,
            trust_remote_code=False, quantization_config=quant, dtype=torch.bfloat16, device_map={"": 0})
        model.config.use_cache = False
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
        model = get_peft_model(model, LoraConfig(task_type=TaskType.CAUSAL_LM, r=16,
            lora_alpha=32, lora_dropout=0.05, bias="none", target_modules=config["lora"]["target_modules"]))
        parameters = [p for p in model.parameters() if p.requires_grad]
        optimizer = bnb.optim.PagedAdamW8bit(parameters, lr=0.0002, weight_decay=0.01)
        scheduler = get_cosine_schedule_with_warmup(optimizer,
            num_warmup_steps=math.ceil(total_steps * 0.05), num_training_steps=total_steps)
        dataset = C5TokenizedDataset(chosen)
        collator = C5CausalLMCollator(tokenizer.pad_token_id)
        def batch(record):
            return {k: v.to(model.device) for k, v in collator([record]).items()}
        def loss_eval(data):
            model.eval(); losses = []
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
                for r in data:
                    check_deadline(); losses.append(finite(model(**batch(r)).loss.item(), "eval loss"))
            return sum(losses) / len(losses)
        progress = {"global_step": 0, "initial_loss": None, "best_checkpoint": None,
                    "validation_candidates": [], "resumed_from": None}
        if args.resume_step is not None:
            cp = run / f"checkpoint-{args.resume_step}"
            progress = verify_checkpoint(cp, context_hash)
            if progress["global_step"] != args.resume_step:
                raise ExecutionError("resume step mismatch")
            from peft import set_peft_model_state_dict
            from safetensors.torch import load_file
            set_peft_model_state_dict(model, load_file(str(cp / "adapter_model.safetensors")))
            state = torch.load(cp / "state.pt", map_location="cpu", weights_only=False)
            optimizer.load_state_dict(state["optimizer"]); scheduler.load_state_dict(state["scheduler"])
            random.setstate(state["python_rng"]); torch.set_rng_state(state["torch_rng"])
            torch.cuda.set_rng_state_all(state["cuda_rng"])
            progress["resumed_from"] = args.resume_step
        else:
            progress["initial_loss"] = loss_eval(dataset)
        def save_checkpoint(step):
            cp = run / f"checkpoint-{step}"
            if cp.exists():
                raise ExecutionError("checkpoint already exists")
            cp.mkdir()
            model.save_pretrained(cp, safe_serialization=True)
            torch.save({"optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(),
                        "python_rng": random.getstate(), "torch_rng": torch.get_rng_state(),
                        "cuda_rng": torch.cuda.get_rng_state_all()}, cp / "state.pt")
            write_json(cp / "progress.json", progress)
            write_json(cp / "lineage.json", checkpoint_manifest(cp, context_hash))
            # Only this run's generated checkpoint directories are rotated.
            cps = sorted((p for p in run.glob("checkpoint-*") if (p / "lineage.json").is_file()),
                         key=lambda p: int(p.name.split("-")[-1]))
            keep = {cp.name, progress.get("best_checkpoint")}
            if phase == "overfit": keep.add("checkpoint-1")
            for p in reversed(cps):
                if len(keep - {None}) < 3: keep.add(p.name)
            for p in cps:
                if p.name not in keep:
                    append_event(run / "metrics.jsonl", {"event": "checkpoint_rotated", "name": p.name,
                        "lineage_sha256": sha256_file(p / "lineage.json")})
                    shutil.rmtree(p)
        validation_records = C5TokenizedDataset([r for r in records if r.split == "validation"])
        while progress["global_step"] < total_steps:
            check_deadline()
            step0 = progress["global_step"]
            epoch, position = divmod(step0, steps_per_epoch)
            order = list(range(len(dataset))); random.Random(20260928 + epoch).shuffle(order)
            indices = order[position * 16:(position + 1) * 16]
            model.train(); optimizer.zero_grad(set_to_none=True); losses = []
            for i in indices:
                check_deadline()
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    loss = model(**batch(dataset[i])).loss
                losses.append(finite(loss.item(), "train loss"))
                (loss / len(indices)).backward()
            grad_norm = finite(torch.nn.utils.clip_grad_norm_(parameters, 1.0).item(), "gradient norm")
            optimizer.step(); scheduler.step(); progress["global_step"] += 1
            step = progress["global_step"]
            append_event(run / "metrics.jsonl", {"step": step, "loss": sum(losses) / len(losses),
                "grad_norm": grad_norm, "learning_rate": scheduler.get_last_lr()[0],
                "elapsed_seconds": time.monotonic() - start})
            if phase == "formal" and step % steps_per_epoch == 0:
                val_loss = loss_eval(validation_records)
                scores, rows = evaluate_families(model, tokenizer, families["validation"], check_deadline)
                candidate = {"step": step, "eval_loss": val_loss, **scores}
                prior = progress["validation_candidates"]
                if not prior or selection_key(candidate) > max(selection_key(c) for c in prior):
                    progress["best_checkpoint"] = f"checkpoint-{step}"
                prior.append(candidate)
                write_json(run / f"validation-{step}.json", {"metrics": candidate, "rows": rows})
            if step == 1 or step % 10 == 0 or step == total_steps or (phase == "formal" and step % steps_per_epoch == 0):
                save_checkpoint(step)
            if args.stop_after_step is not None and step == args.stop_after_step:
                break
        completed = progress["global_step"] == total_steps
        result = {"phase": phase, "experiment_id": EXPERIMENT_ID, "contract_id": CONTRACT_ID,
                  "context_sha256": context_hash, "global_step": progress["global_step"],
                  "completed": completed, "passed": False,
                  "resumed_from": progress["resumed_from"], "initial_loss": progress["initial_loss"],
                  "training_records": len(chosen), "training_families": len({r.family_id for r in chosen}),
                  "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                  "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                  "final_holdout_rows_read": 0, "rhino_called": False}
        if completed:
            result["final_loss"] = loss_eval(dataset)
            result["relative_loss_decrease"] = 1 - result["final_loss"] / result["initial_loss"]
            if phase == "overfit":
                result["passed"] = result["relative_loss_decrease"] >= 0.25 and args.resume_step == 1
            elif phase == "system":
                result["validation_loss"] = loss_eval(validation_records)
                result["passed"] = True
            else:
                best = progress["best_checkpoint"]
                verify_checkpoint(run / best, context_hash)
                adapter_hashes = {name: sha256_file(run / best / name)
                                  for name in ("adapter_model.safetensors", "adapter_config.json")}
                registry = {"experiment_id": EXPERIMENT_ID, "contract_id": CONTRACT_ID,
                            "base_revision": BASE_MODEL_REVISION, "selected_checkpoint": best,
                            "adapter_sha256": digest(adapter_hashes), "files": adapter_hashes,
                            "validation_candidates": progress["validation_candidates"],
                            "selection_order": ["sequence_exact", "arguments_exact", "parse_exact", "eval_loss"],
                            "tie_break": "earliest_checkpoint", "context_sha256": context_hash,
                            "final_holdout_rows_read": 0, "product_route_authorized": False}
                write_json(run / "registry.json", registry, exclusive=True)
                result.update(passed=True, registry=registry)
        result["seconds_this_segment"] = time.monotonic() - start
        write_json(run / ("result.json" if completed else "paused.json"), result, exclusive=completed)
        return result
    except BaseException as exc:
        write_json(run / ("failure-" + segment + ".json"), {"phase": phase, "passed": False,
                   "error_type": type(exc).__name__, "error": str(exc),
                   "final_holdout_rows_read": 0, "context_sha256": context_hash})
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_alarm); signal.signal(signal.SIGTERM, old_term)
        append_event(events_path, {"event": "finish", "segment_id": segment, "phase": phase,
                                  "seconds": time.monotonic() - start, "passed": result.get("passed", False)})
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN); lock.close()
