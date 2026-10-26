#!/usr/bin/env python3
"""CPU-only audit of public development inputs using the pinned tokenizer.

The remote stdin program loads a tokenizer, never model weights or a model
backend. No private tasks/logs, remote file upload, inference or grant. This
audits text length for the analytic public scene, not a real Rhino readback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from training.c5_contract import CORE_INVOCATION_TOOLS, DECODE_CONFIG, render_invocation, render_selection
from training.c5_inventory import load_public_mcp_tools
from training.c5_rhino_adapter import step_input
from training.lora_dev_feedback import render_step
from training.lora_development_cases import build_cases, fixture_design


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class TemplateCapture:
    """Capture original renderer calls; dummy counts are not the audit result."""
    def apply_chat_template(self, messages, **kwargs):
        return canonical({"messages": messages, "kwargs": kwargs})

    def __call__(self, text, **kwargs):
        return {"input_ids": [0]}


def public_contexts(*, native_floats=False):
    _, scene, _ = fixture_design()
    if native_floats:
        # NativeDoc.readback -> point() uses float coordinates. This is still
        # an analytic representation check, never an observed Rhino capture.
        for obj in scene['objects']:
            for key in ('min', 'max'):
                obj[key] = [float(value) for value in obj[key]]
    binding = {"document_key": "a" * 64, "revision": 0, "scene_sha256": "b" * 64}
    rows = []
    for entry in build_cases():
        case, task = entry["case"], entry["case"]["task_text"]
        rows.extend([
            {"family_id": case["family_id"], "system": "original", "progress": "scene_unchanged",
             "user_step": step_input(task, scene)},
            {"family_id": case["family_id"], "system": "read_progress_v1", "progress": "no_previous_step",
             "user_step": render_step(task, scene)},
        ])
        if case["max_steps"] < 2:
            continue
        # Enumerate every successful read allowed by this two-object scene,
        # rather than using an expected answer to choose the preceding call.
        for name, args in [("get_scene_summary", {}), ("get_bounding_box", {"object_id": "box-1"}),
                           ("get_bounding_box", {"object_id": "box-2"})]:
            previous = {"step_index": 0, "policy_denied": False,
                "observation": {"status": "schema_valid_not_authorized", "name": name, "arguments": args,
                    "scene_binding": binding, "repair_count": 0, "dispatch_count": 0},
                "receipt": {"status": "done", "payload": {"operation": name, "arguments": args,
                    "expected": binding}, "before_state": binding, "after_state": binding,
                    "before": scene, "after": scene}}
            rows.append({"family_id": case["family_id"], "system": "read_progress_v1",
                "progress": name + ":" + args.get("object_id", "scene"),
                "user_step": render_step(task, scene, step_index=1, previous_step=previous,
                                         current_binding=binding)})
    return rows


REMOTE = r'''
import hashlib,json,os,sys,sysconfig
from pathlib import Path
for key,value in {'USE_TORCH':'0','USE_TF':'0','USE_FLAX':'0','HF_HUB_OFFLINE':'1',
                  'TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1','TOKENIZERS_PARALLELISM':'false'}.items():
    os.environ[key]=value
blocked={'torch','tensorflow','jax','peft','bitsandbytes'}
# A None sentinel blocks actual import and lets find_spec report unavailable;
# raising from a finder also rejects harmless availability checks.
for name in blocked: sys.modules[name]=None
sys.path.append(sysconfig.get_path('purelib'))  # -S skips site hooks and .pth execution.
from transformers import AutoTokenizer
payload=json.load(sys.stdin)
snapshot=Path('/data/hf-cache/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots/c03e6d358207e414f1eca0bb1891e29f1db0e242')
for name,expected in payload['tokenizer_files'].items():
    assert Path(name).name==name and name in {'tokenizer.json','tokenizer_config.json','vocab.json','merges.txt','config.json','generation_config.json'}
    assert hashlib.sha256((snapshot/name).read_bytes()).hexdigest()==expected
tokenizer=AutoTokenizer.from_pretrained(snapshot,local_files_only=True,trust_remote_code=False)
if tokenizer.pad_token_id is None: tokenizer.pad_token=tokenizer.eos_token
tokenizer.padding_side='right'
results=[]
for row in payload['contexts']:
    counts=[]; hashes=[]
    for item in row['templates']:
        prompt=tokenizer.apply_chat_template(item['messages'],**item['kwargs'])
        assert row['user_step'] in prompt, 'public input/feedback lost in chat template'
        ids=tokenizer(prompt,add_special_tokens=False,truncation=False)['input_ids']
        counts.append(len(ids)); hashes.append(hashlib.sha256(prompt.encode()).hexdigest())
    results.append({k:row[k] for k in ('family_id','system','progress')} | {'prompt_tokens':counts,'prompt_sha256':hashes})
assert not any(n.split('.')[0] in blocked and value is not None for n,value in sys.modules.items())
print(json.dumps({'tokenizer_class':type(tokenizer).__name__,'contexts':results,
    'model_backend_imported':False,'model_loaded':False,'generation_calls':0,
    'source_text_preserved_in_every_prompt':True,'truncation':False},sort_keys=True))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-control", type=Path, required=True)
    parser.add_argument("--ssh-target", required=True)
    parser.add_argument("--ssh-port", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-floats", action="store_true")
    args = parser.parse_args()
    if not args.ssh_control.is_socket() or args.output.exists():
        raise ValueError("authenticated control socket and new output path required")
    capture, tools = TemplateCapture(), load_public_mcp_tools()
    contexts = public_contexts(native_floats=args.native_floats)
    for row in contexts:
        row["templates"] = [json.loads(render_selection(capture, row["user_step"], tools).prompt)] + [
            json.loads(render_invocation(capture, row["user_step"], tools, name).prompt) for name in CORE_INVOCATION_TOOLS]
    resources = json.loads((ROOT / "eval/lora-development/readonly-resources-20261026.json").read_text())
    files = {n: s for n, s in resources["model_assets"]["base_files"].items()
             if n in {"tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "config.json", "generation_config.json"}}
    payload = {"contexts": contexts, "tokenizer_files": files}
    command = "/data/conda-envs/rhinocoder/bin/python3.11 -I -S -B -c " + shlex.quote(REMOTE)
    result = subprocess.run(["ssh", "-T", "-S", str(args.ssh_control), "-o", "BatchMode=yes", "-o",
        "StrictHostKeyChecking=yes", "-p", str(args.ssh_port), args.ssh_target, command],
        input=canonical(payload), text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError("CPU tokenizer audit refused: " + result.stderr[-2200:])
    report = json.loads(result.stdout)
    assert [(r["family_id"], r["system"], r["progress"]) for r in report["contexts"]] == [
        (r["family_id"], r["system"], r["progress"]) for r in contexts]
    reserves = [DECODE_CONFIG["selector_max_new_tokens"]] + [DECODE_CONFIG["invocation_max_new_tokens"]] * 12
    assert len(contexts) == 28 and all(len(r["prompt_tokens"]) == len(reserves) for r in report["contexts"])
    margins = [2048 - count - reserve for r in report["contexts"] for count, reserve in zip(r["prompt_tokens"], reserves)]
    sources = ["tools/audit_lora_development_token_budget.py", "training/lora_dev_feedback.py",
               "training/lora_development_cases.py", "training/c5_contract.py", "training/c5_inventory.py",
               "training/tool_selector_v4_candidate.py", "training/tool_contract_v3_candidate.py",
               "training/tool_contract_candidate.py", "training/c5_rhino_adapter.py",
               "plugin/rhino_listener/c5_research_native.py"]
    report.update({"schema_version": 1, "scope": "public_development_CPU_tokenization_only",
        "input_sha256": hashlib.sha256(canonical(payload).encode()).hexdigest(), "tokenizer_files": files,
        "source_sha256": {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in sources},
        "prompt_order": ["selector"] + list(CORE_INVOCATION_TOOLS), "reserves": reserves,
        "checked_prompts": len(margins), "all_fit": min(margins) >= 0, "minimum_headroom_tokens": min(margins),
        "max_selector_prompt_tokens": max(r["prompt_tokens"][0] for r in report["contexts"]),
        "max_invocation_prompt_tokens": max(max(r["prompt_tokens"][1:]) for r in report["contexts"]),
        "synthetic_predecessor_facts_not_native_receipts": True, "actual_execution_authorized": False,
        "scene_numeric_representation": "native_float_coordinates" if args.native_floats else "analytic_integer_coordinates",
        "preparation_history": ["Initial CPU audit stopped before tokenization: raising from the import guard rejected a harmless torch availability query. None sentinels preserve the import prohibition and allow availability checks; no model backend or weights were loaded."],
        "limitations": ["analytic public fixture only; live scene must match", "no model decisions or latency measured",
                        "all core invocation schemas audited for possible wrong selections; model write budget remains zero"]})
    with args.output.open("x") as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(canonical({k: report[k] for k in ("checked_prompts", "all_fit", "minimum_headroom_tokens",
        "max_selector_prompt_tokens", "max_invocation_prompt_tokens", "generation_calls", "actual_execution_authorized")}))


if __name__ == "__main__":
    main()
