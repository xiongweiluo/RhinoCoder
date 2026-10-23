"""Worker-side selected-subset/order guard, before raw request claim/generation."""

from plugin.rhino_listener.c5_research_native import require


def validate_scheduled_request(sent, plans, order, indices, attempted):
    require(
        type(order) is list
        and len(order) == 40
        and {s["slot_id"] for s in order} == set(plans),
        "slot_worker_complete_order",
    )
    require(
        type(indices) is list
        and indices == sorted(set(indices))
        and all(type(i) is int and 0 <= i < 40 for i in indices),
        "slot_worker_indices",
    )
    labels = [order[i]["slot_id"] for i in indices]
    slot = sent.get("slot_id")
    require(slot in labels, "slot_worker_outside_approved_subset")
    if not attempted or attempted[-1] != slot:
        # Local fixture failure can have zero requests: later indices may be skipped,
        # but no prior index can be regenerated and no outside slot can be inserted.
        require(
            slot not in attempted
            and (not attempted or labels.index(slot) > labels.index(attempted[-1])),
            "slot_worker_replay_or_order",
        )
        attempted.append(slot)


def audit_exported_step(state, slot_id, index, freeze):
    from plugin.rhino_listener.c5_research_native import digest
    from plugin.rhino_listener.c5_research_channel import read_json

    key = digest({"slot": slot_id, "step": index, "freeze": digest(freeze)})
    sent = read_json(state, key + "-model-request.json")
    response = read_json(state, key + "-model-response.json")
    value = read_json(state, key + "-remote-evidence.json")
    require(
        set(value) == {"status", "request_sha256", "key", "records"}
        and value["status"] == "formal_raw_step_evidence"
        and value["key"] == key
        and value["request_sha256"]
        == digest(
            {
                "kind": "formal_export_step",
                "study_id": freeze["study_id"],
                "runtime_freeze_sha256": digest(freeze),
                "key": key,
            }
        ),
        "slot_raw_export_scope",
    )
    records = value["records"]
    names = {
        key + "-request.json",
        key + "-response.json",
        "generation-" + key + ".claim.json",
    }
    require(
        records.get(key + "-request.json") == sent
        and records.get(key + "-response.json") == response
        and records.get("generation-" + key + ".claim.json")
        == {"request_sha256": digest(sent), "replay_allowed": False},
        "slot_raw_export_original_records",
    )
    for receipt in response["generation_receipts"]:
        stage = receipt["stage"]
        names.update(
            {key + "-" + stage + "-attempt.json", key + "-" + stage + "-raw.json"}
        )
        require(
            records.get(key + "-" + stage + "-raw.json") == receipt
            and records.get(key + "-" + stage + "-attempt.json")
            == {
                "stage": stage,
                "prompt_sha256": receipt["prompt_sha256"],
                "attempted": True,
                "tokens": 0,
                "seconds": 0.0,
            },
            "slot_raw_export_generation_receipt",
        )
    require(set(records) == names, "slot_raw_export_exact_population")
    return digest(value)
