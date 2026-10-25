"""CPU-only B admission/one-attempt controls, never field proof or authorization."""
import copy
import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from plugin.rhino_listener.research_safety import ResearchSafetyError, canonical_hash
from tools import r_research_two_write_v2 as module
from tools.r4_v5_ssh_no_write_session import _private_publish, _private_read
from tools.r_research_two_write_smoke import SPEC as HISTORIC_A


def prepared(tmp_path, monkeypatch):
    root, state, batch = (tmp_path/name for name in ("root", "state", "batch"))
    for path in (root, state, batch):
        path.mkdir(mode=0o700)
    (root/"module.py").write_text("pass\n")
    inventory = {"module.py": hashlib.sha256(b"pass\n").hexdigest()}
    freeze = {"schema_version": 2, "probe_spec": copy.deepcopy(module.SPEC),
              "probe_spec_sha256": canonical_hash(module.SPEC), "policy": copy.deepcopy(module.POLICY),
              "source_revision": "a"*40, "source_inventory": inventory,
              "source_inventory_sha256": canonical_hash(inventory)}
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "STATE_DIR", state)
    monkeypatch.setattr(module, "read_freeze", lambda: freeze)
    monkeypatch.setattr(module, "source_inventory", lambda _: inventory)
    monkeypatch.setattr(module, "verify_loaded_sources", lambda *args: None)
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: b"pass\n")
    _private_publish(batch, "bootstrap.json", {"version": 2, "scope": module.SPEC["scope"],
        "model_invocation_allowed": False, "formal_quality_claim": False, "initial_active_sha256": "a"*64})
    _private_publish(batch, "source-inventory.json", inventory)
    approval = {"authorized_by": "repository_owner", "approved": True,
        "probe_spec_sha256": canonical_hash(module.SPEC), "runtime_freeze_sha256": canonical_hash(freeze),
        "authorization_basis": "explicit owner reply approving fixed two-write research safety probe"}
    return freeze, approval, state, batch


@pytest.mark.parametrize("field,value", [("authorized_by", "codex"), ("approved", False),
    ("probe_spec_sha256", canonical_hash(HISTORIC_A)), ("runtime_freeze_sha256", "f"*64),
    ("authorization_basis", "blanket request to complete everything")])
def test_owner_must_bind_new_spec_and_freeze_before_claim(tmp_path, monkeypatch, field, value):
    _, approval, state, batch = prepared(tmp_path, monkeypatch)
    approval[field] = value
    monkeypatch.setattr(module, "run_engine", lambda *args, **kwargs: pytest.fail("must not open"))
    with pytest.raises(ResearchSafetyError):
        module.run(batch, approval)
    assert list(state.iterdir()) == []


@pytest.mark.parametrize("mutation", ["spec", "policy", "inventory", "digest", "commit", "version", "extra"])
def test_changed_freeze_fails_even_when_approval_hash_matches(tmp_path, monkeypatch, mutation):
    freeze, approval, state, batch = prepared(tmp_path, monkeypatch)
    if mutation == "spec": freeze["probe_spec"]["steps"][0]["width"] += 1
    if mutation == "policy": freeze["policy"]["write_retries"] = 1
    if mutation == "inventory": freeze["source_inventory"] = {}
    if mutation == "digest": freeze["source_inventory_sha256"] = "f"*64
    if mutation == "commit": monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: b"drift")
    if mutation == "version": freeze["schema_version"] = True
    if mutation == "extra": freeze["tasks"] = []
    approval["runtime_freeze_sha256"] = canonical_hash(freeze)
    with pytest.raises(ResearchSafetyError): module.run(batch, approval)
    assert list(state.iterdir()) == []


@pytest.mark.parametrize("mutation", ["source", "request", "response", "failure", "scope", "model"])
def test_used_or_different_controller_fails_before_claim(tmp_path, monkeypatch, mutation):
    _, approval, state, batch = prepared(tmp_path, monkeypatch)
    if mutation == "source":
        (batch/"source-inventory.json").unlink()
        _private_publish(batch, "source-inventory.json", {})
    elif mutation in {"scope", "model"}:
        value = _private_read(batch/"bootstrap.json")
        value["scope" if mutation == "scope" else "model_invocation_allowed"] = "product" if mutation == "scope" else True
        (batch/"bootstrap.json").unlink()
        _private_publish(batch, "bootstrap.json", value)
    else: _private_publish(batch, mutation+"-001.json", {})
    with pytest.raises(ResearchSafetyError): module.run(batch, approval)
    assert list(state.iterdir()) == []


@pytest.mark.parametrize("interrupted", [False, True])
def test_claim_permanently_prevents_replay_even_before_output(tmp_path, monkeypatch, interrupted):
    _, approval, state, batch = prepared(tmp_path, monkeypatch)
    calls = []
    def engine(*args, **kwargs):
        assert (state/module.CLAIM_NAME).exists()
        assert kwargs["spec"] == module.SPEC
        calls.append(1)
        if interrupted: raise RuntimeError("CPU simulated infrastructure interruption")
        return {"status": "synthetic_only_not_field_proof"}
    monkeypatch.setattr(module, "run_engine", engine)
    if interrupted:
        with pytest.raises(RuntimeError): module.run(batch, approval)
    else: module.run(batch, approval)
    with pytest.raises(FileExistsError): module.run(batch, approval)
    assert calls == [1] and len(list(state.iterdir())) == 1


def test_concurrent_admissions_only_one_engine_call(tmp_path, monkeypatch):
    _, approval, state, batch = prepared(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(module, "run_engine", lambda *a, **k: calls.append(1))
    def attempt():
        try: module.run(batch, approval); return "claimed"
        except FileExistsError: return "refused"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: attempt(), range(2))) == ["claimed", "refused"]
    assert calls == [1] and (state/module.CLAIM_NAME).is_file()


def test_direct_shared_engine_cannot_bypass_or_resume_admission(tmp_path, monkeypatch):
    freeze, approval, state, batch = prepared(tmp_path, monkeypatch)
    output = state/module.OUTPUT_NAME
    with pytest.raises(FileNotFoundError): module.begin_engine(batch, output, approval, module.SPEC)
    claim = module.claim_value(batch, approval, canonical_hash(freeze))
    _private_publish(state, module.CLAIM_NAME, claim)
    module.begin_engine(batch, output, approval, module.SPEC)
    assert not output.exists()  # Even a death here cannot authorize a resume.
    with pytest.raises(FileExistsError): module.begin_engine(batch, output, approval, module.SPEC)
    changed = {**module.SPEC, "probe_id": "RSDEV-UNREGISTERED"}
    with pytest.raises(ResearchSafetyError): module.begin_engine(batch, output, approval, changed)


def test_readonly_auditor_accepts_explicit_b_without_changing_a(tmp_path, monkeypatch):
    from eval import test_research_two_write_audit as fixtures
    from tools.audit_r_research_two_write import audit
    monkeypatch.setattr(fixtures, "SPEC", module.SPEC)
    batch, output, _ = fixtures.fixture(tmp_path, monkeypatch)
    value = audit(batch, output/"result.json", spec=module.SPEC)
    assert value["probe_id"] == module.SPEC["probe_id"] and not value["c5_6_authorized"]
    assert HISTORIC_A["probe_id"].endswith("-A") and canonical_hash(HISTORIC_A) == "c93c7f43eb9527f2fff15c2a28f8bcc3fe8ef6c12221b3fdc276dca3993b861f"
