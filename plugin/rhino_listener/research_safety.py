"""Python-3.9-compatible research handoff primitives, separate from historic R v2.

These checks do not grant consent or execute geometry. A future versioned
runner must supply real UI-thread receipts; synthetic tests are not a field GO.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{64}\Z")


class ResearchSafetyError(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise ResearchSafetyError(reason)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def source_inventory(root: Path):
    """Conservative complete tracked Python inventory; never packages dirty assets."""
    names = subprocess.check_output(["git", "ls-files", "-z", "--", "agent", "training", "tools", "plugin", "mcp_server", "requirements-lock.txt"],
                                    cwd=root).decode().split("\0")
    result = {}
    for name in sorted(n for n in names if n.endswith(".py") or n == "requirements-lock.txt"):
        path = root/name
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
                "tracked source unavailable or unsafe")
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    require(bool(result), "empty source inventory")
    return result


def verify_loaded_sources(root: Path, inventory: dict, modules):
    """Reject execution from undeclared/untracked local modules or changed bytes."""
    root = root.resolve()
    for name, expected in inventory.items():
        path = root/name
        require(not Path(name).is_absolute() and ".." not in Path(name).parts
                and SHA.fullmatch(str(expected)) is not None
                and not path.is_symlink() and path.is_file() and path.resolve().is_relative_to(root)
                and hashlib.sha256(path.read_bytes()).hexdigest() == expected, "source drift")
    for module in modules:
        filename = getattr(module, "__file__", None)
        if filename is None:
            continue
        path = Path(filename).resolve()
        if path.is_relative_to(root):
            relative = path.relative_to(root).as_posix()
            require(relative in inventory, "undeclared loaded local dependency")
    return {"source_files": len(inventory), "source_inventory_sha256": canonical_hash(inventory)}


def cleanup_plan(*, open_published, case_id, opened=None, closed=None):
    """Pure cleanup decision. An unknown session is never targeted by guessed IDs.

    Ordered requests are a plan, NOT evidence that a fixture closed. A timeout
    or invalid receipt remains a failed/uncertain run until independent review.
    """
    if not open_published:
        return {"state": "no_fixture_published", "actions": ["stop"], "cleanup_verified": False}
    verified = (isinstance(opened, dict) and opened.get("status") == "opened"
                and opened.get("case_id") == case_id and opened.get("fixture") == "empty"
                and isinstance(opened.get("session_dir"), str)
                and Path(opened["session_dir"]).is_absolute())
    if not verified:
        return {"state": "identity_unknown_manual_cleanup", "actions": [], "cleanup_verified": False}
    if (isinstance(closed, dict) and closed.get("status") == "closed"
            and closed.get("case_id") == case_id and closed.get("session_dir") == opened["session_dir"]
            and closed.get("key_removed") is True):
        return {"state": "fixture_closed_wait_controller_stop", "actions": ["stop"],
                "cleanup_verified": False}
    return {"state": "known_fixture_ordered_cleanup_pending", "actions": ["close", "stop"],
            "cleanup_verified": False}


def verify_final_active_capture(capture, *, case_id, session_dir, initial_sha256):
    require(isinstance(capture, dict) and capture.get("case_id") == case_id
            and capture.get("session_dir") == str(session_dir)
            and capture.get("on_rhino_main_thread") is True
            and capture.get("capture_scope") == "same_ui_callback_before_and_after_fixture_close",
            "final capture identity/thread/scope invalid")
    require(SHA.fullmatch(str(initial_sha256)) is not None
            and capture.get("initial_active_sha256") == initial_sha256
            and capture.get("before_close_active_sha256") == initial_sha256
            and capture.get("after_close_active_sha256") == initial_sha256,
            "active document raw digests differ")
    require(type(capture.get("close_seq")) is int and capture["close_seq"] > 0
            and capture.get("fixture_closed") is True and capture.get("key_removed") is True,
            "close/key evidence missing")
    return True


def _objects(scene):
    require(isinstance(scene, dict) and isinstance(scene.get("objects"), list), "missing geometric readback")
    indexed = {}
    for row in scene["objects"]:
        require(isinstance(row, dict) and set(row) == {"alias", "min", "max"}
                and isinstance(row["alias"], str) and row["alias"] not in indexed,
                "invalid or duplicate geometric alias")
        for bound in ("min", "max"):
            values = row[bound]
            require(isinstance(values, list) and len(values) == 3
                    and all(type(x) in (int, float) and math.isfinite(x) for x in values),
                    "invalid/nonfinite geometry")
        require(all(a <= b for a, b in zip(row["min"], row["max"])), "inverted bounds")
        indexed[row["alias"]] = row
    return indexed


def verify_exact_transition(operation, arguments, before, after):
    """Independent arithmetic for the old R fixture's two supported write tools.

    Deliberately fails for the other C5 core tools: this is not a claim that
    the old fixture can execute the frozen twelve-tool C5 research scope.
    """
    prior, current = _objects(before), _objects(after)
    if operation == "create_box":
        require(set(arguments) == {"width", "depth", "height"}, "box parameters differ")
        values = [arguments[k] for k in ("width", "depth", "height")]
        require(all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in values),
                "invalid box dimensions")
        alias = "box-"+str(len(prior)+1)
        expected = dict(prior)
        expected[alias] = {"alias": alias, "min": [0., 0., 0.], "max": values}
    elif operation == "move_object":
        require(set(arguments) == {"alias", "translate_x", "translate_y", "translate_z"}, "move parameters differ")
        alias = arguments["alias"]
        require(alias in prior, "unknown target alias")
        vector = [arguments[k] for k in ("translate_x", "translate_y", "translate_z")]
        require(all(type(x) in (int, float) and math.isfinite(x) for x in vector), "invalid move vector")
        expected = dict(prior)
        expected[alias] = {"alias": alias, **{k: [a+b for a, b in zip(prior[alias][k], vector)]
                                             for k in ("min", "max")}}
    else:
        raise ResearchSafetyError("tool_not_supported_by_R_research_fixture")
    require(current.keys() == expected.keys(), "geometric object set differs")
    for alias in expected:
        for bound in ("min", "max"):
            require(all(math.isclose(a, b, rel_tol=0., abs_tol=1e-7)
                        for a, b in zip(current[alias][bound], expected[alias][bound])), "exact geometry differs")
    return True


def verify_write_binding(*, record, execution, ledger_row, consent_events,
                         consent_request, envelope_payload):
    """Do not trust readback_verified/ledger_state booleans without cross-linking."""
    request_id = record.get("request_id")
    require(isinstance(request_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{24,128}", request_id) is not None,
            "invalid request ID")
    key = hashlib.sha256(request_id.encode()).hexdigest()
    require(envelope_payload.get("request_id") == consent_request.get("request_id") == request_id
            and ledger_row.get("idempotency_key") == key
            and execution.get("idempotency_key_sha256") == hashlib.sha256(key.encode()).hexdigest(),
            "execution/ledger request IDs differ")
    require(record.get("operation") == execution.get("operation") == envelope_payload.get("operation")
            == consent_request.get("tool_name") and record.get("signed_arguments") == envelope_payload.get("arguments"),
            "execution operation/arguments differ")
    arguments = record["signed_arguments"]
    require(isinstance(arguments, dict), "invalid signed arguments")
    consent_arguments = dict(arguments)
    if record["operation"] == "move_object":
        require("alias" in consent_arguments, "missing move alias")
        consent_arguments["object_id"] = consent_arguments.pop("alias")
    require(consent_request.get("status") == "consumed"
            and consent_request.get("arguments_sha256") == canonical_hash(consent_arguments)
            and record.get("task_sha256") == envelope_payload.get("task_sha256") == consent_request.get("task_sha256")
            and SHA.fullmatch(str(record.get("task_sha256"))) is not None, "consent task/arguments differ")
    require(record.get("before_scene_sha256") == execution.get("before_scene_sha256")
            == ledger_row.get("expected_sha256") == envelope_payload.get("scene_sha256")
            == consent_request.get("scene_sha256")
            and SHA.fullmatch(str(record.get("before_scene_sha256"))) is not None
            and record.get("before_revision") == ledger_row.get("expected_revision")
            == envelope_payload.get("scene_revision") == consent_request.get("scene_revision")
            # Empty Rhino fixtures begin at zero, as do the envelope and
            # GivenScene contracts. Keep all identity checks and reject
            # negative, boolean and floating-point revisions.
            and type(record.get("before_revision")) is int and record["before_revision"] >= 0
            and record.get("document_key") == ledger_row.get("document_key") == envelope_payload.get("document_key")
            and SHA.fullmatch(str(record.get("document_key"))) is not None,
            "pre-scene chain differs")
    require(record.get("after_scene_sha256") == execution.get("after_scene_sha256")
            and SHA.fullmatch(str(record.get("after_scene_sha256", ""))) is not None,
            "post-scene chain differs")
    require(ledger_row.get("state") == execution.get("ledger_state") == "done"
            and execution.get("status") == "done"
            and ledger_row.get("request_sha256") == canonical_hash({
                "operation": record["operation"], "arguments": arguments})
            and execution.get("result_sha256") == ledger_row.get("result_sha256")
            and SHA.fullmatch(str(execution.get("result_sha256"))) is not None,
            "ledger does not bind signed payload/result")
    require([e.get("event_type") for e in consent_events] == [
        "requested", "approved", "consumed", "signed_handoff_issued"]
        and all(e.get("request_id") == record["request_id"] for e in consent_events),
        "consent events do not bind unique request")
    return True
