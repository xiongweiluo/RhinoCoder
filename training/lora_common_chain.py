"""Explicit full-tool strategy for the existing development controller.

Reuse original permissions, native ledger audit and scorer. This is not a
live entry or grant; callers must bind approved source, case and state roots.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from plugin.rhino_listener.c5_research_native import CORE, READS, digest, require
from training import lora_common_wire as wire
from training.c5_formal20_prepermission import rejection
from training.c5_inventory import load_public_mcp_tools
from training.c5_modelbridge_joint_audit import semantic
from training.c5_research_audit import _tables, audit_permission_tables
from training.c5_research_permission import ResearchSigner, SceneView
from training.consent_candidate import ConsentStore
from training.lora_comparison_plan import compile_cases, capacity


class CommonChain:
    wire = wire

    def __init__(self, plan, compiled, cases, directory):
        require(compile_cases(plan, cases) == compiled, 'complete validated case binding differs')
        self.cases = {c['family_id']: c for c in cases}
        self.study, self.directory = plan['study_id'], Path(directory)
        self.plan = plan
        self.capture_max = capacity(plan)['signer_captures_per_step_max']
        self.stores, self.signers = {}, {}

    def work_guard(self):
        if self.study == 'lora-common-final-comparison-v1':
            from plugin.rhino_listener.lora_development_runtime import common_configuration
            from training.lora_comparison_storage import check_evidence_budget
            check_evidence_budget(self.directory.parent, common_configuration(self.plan))

    def start(self, slot):
        path = self.directory / (slot + '.consent.sqlite3')
        require(not path.exists() and not path.is_symlink(), 'new slot permission database required')
        self.stores[slot] = ConsentStore(path, load_public_mcp_tools())
        # Empty tasks still need an auditable, empty handoff table.
        with self.stores[slot]._tx() as db:
            db.execute('CREATE TABLE c5_model_handoff (observation_sha256 TEXT PRIMARY KEY, state TEXT NOT NULL, request_id TEXT UNIQUE, payload_sha256 TEXT)')

    def allowed(self, observed, case, receipts, current, schemas):
        op = observed['name']
        return (op in CORE and sum((r['payload']['operation'] in READS) == (op in READS) for r in receipts)
                < case['max_reads' if op in READS else 'max_writes']
                and rejection(op, observed['arguments'], current['native'], schemas) is None)

    def issue(self, controller, slot, sent, observed, case):
        captures = [0]
        def capture():
            captures[0] += 1
            require(captures[0] <= self.capture_max, 'bounded signer capture count exceeded')
            return controller.exchange(slot, 'capture')[0]
        class Proxy:
            def snapshot(self): return capture()['state']
            def semantic_scene(self): return semantic(capture()['native'])
        proxy = Proxy()
        signer = self.signers.get(slot)
        if signer is None:
            signer = ResearchSigner(self.stores[slot], SceneView(proxy, proxy.semantic_scene),
                controller.secret, controller.runtime, sent['task'], max_reads=case['max_reads'],
                max_writes=case['max_writes'], late_ttl=True)
            self.signers[slot] = signer
        else:
            signer.scene = SceneView(proxy, proxy.semantic_scene)
        return signer.issue(observed, schemas=controller.schemas, step_request_sha256=digest(sent))

    def audit_receipt(self, receipt, envelope, observation, before):
        require(receipt.get('status') == 'done' and receipt.get('payload') == envelope['payload']
                and receipt['payload']['operation'] == observation['name']
                and receipt['payload']['arguments'] == observation['arguments']
                and receipt['before_state'] == before['state'] == observation['scene_binding']
                and digest(receipt['before']) == digest(before['native'])
                and receipt['result_sha256'] == digest(receipt['result']), 'actual common receipt differs')

    def audit_ledger(self, slot, ledger, receipts, runtime):
        consent = _tables(self.directory / (slot + '.consent.sqlite3'),
                          ('consent_requests', 'consent_events', 'c5_model_handoff'))
        return audit_permission_tables(consent, ledger, receipts,
            task_sha256=hashlib.sha256(self.cases[self.cell_family[slot]]['task_text'].encode()).hexdigest(),
            owner_freeze_sha256=runtime)

    def bind_schedule(self, schedule):
        self.cell_family = {c['slot_id']: c['family_id'] for c in schedule}
