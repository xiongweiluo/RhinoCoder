"""One owner-approved development scope across startup-only revisions.

Python 3.9, no model/Rhino imports. Live entries never initialize this ledger.
Load intents and slot claims are permanent; a new revision cannot reset them.
"""
import ast
from contextlib import contextmanager
import fcntl
import os
import stat
from pathlib import Path

from .c5_research_channel import private_directory, publish_json, read_json
from .c5_research_native import digest, require

CAMPAIGN = 'lora-development-startup-repair-20261026-v1'
ROOTS = {'mac': '/Users/xiongweiluo/RhinoCoder/data/lora-development-20261026-campaign',
         'gpu': '/data/lora-development-20261026-campaign'}
BASIS = 'repository_owner_approved_campaign_scope_and_targeted_startup_repairs'
MUTABLE = (
    'training/lora_development_loader.py', 'training/lora_development_assets.py',
    'training/lora_development_gpu_entry.py',
    'tools/run_lora_development_mac.py', 'tools/run_lora_development_gpu.py',
    'tools/run_lora_development_rhino.py', 'tools/run_lora_development_rhino_wrapper.py',
    'tools/build_lora_development_package.py', 'tools/check_lora_development_source.py')
CONTRACT_KEYS = ('study_id', 'development_plan', 'model_identities', 'assets', 'model_path_bindings',
    'loader_policy', 'gpu_hardware', 'native_scope', 'limits', 'lease_end_epoch',
    'resource_policy', 'host_policy', 'stop_policy', 'evidence_policy', 'historical_family_overlap')


def contract(package):
    return {**{key: package[key] for key in CONTRACT_KEYS}, 'environments': {
        key: {name: value[name] for name in ('python', 'environment_sha256')}
        for key, value in package['endpoints'].items()}}


def owner_record(policy):
    return {'actor': 'repository_owner', 'approved': True, 'campaign_id': CAMPAIGN,
            'policy_sha256': digest(policy), 'approval_basis': BASIS}


def fragments(path):
    """Normalize AST across 3.9/3.11/3.13; protect inference inside the loader."""
    def value(node):
        if isinstance(node, ast.AST):
            return [type(node).__name__, {k: value(v) for k, v in ast.iter_fields(node) if k != 'type_params'}]
        if isinstance(node, list): return [value(n) for n in node]
        return node
    tree = ast.parse(Path(path).read_text())
    nodes = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'load': nodes['load'] = digest(value(node))
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'POLICY' for t in node.targets):
            nodes['POLICY'] = digest(value(node))
    require(set(nodes) == {'load', 'POLICY'}, 'fixed inference and policy fragments required')
    return nodes


def validate(package):
    policy = package['campaign_policy']
    require(type(policy) is dict and set(policy) == {'schema_version', 'campaign_id', 'roots',
        'baseline_loads', 'max_loads', 'baseline_predecessors', 'contract', 'baseline_source_files',
        'mutable_startup_paths', 'loader_fragments'}, 'complete campaign policy required')
    require(policy['schema_version'] == 1 and policy['campaign_id'] == CAMPAIGN
            and policy['roots'] == ROOTS and type(policy['baseline_loads']) is int
            and type(policy['max_loads']) is int and policy['baseline_loads'] == 3 and policy['max_loads'] == 5,
            'fixed cross-revision three-consumed/five-total campaign required')
    require(policy['mutable_startup_paths'] == list(MUTABLE) and contract(package) == policy['contract'],
            'research contract changed; new owner approval required')
    require(package['limits']['gpu_residency_seconds'] is None
            and package['limits']['max_load_attempts'] == 1
            and package['limits']['max_infrastructure_recoveries'] == 0
            and package['resource_policy'] == {'lease_paid': True, 'additional_cost_ceiling': None,
                'new_paid_service_or_renewal': False, 'historical_budget_reuse': False},
            'no total time/cost cap, one launch per reviewed revision and no automatic purchase required')
    rev = package['revision_id']
    require(type(rev) is int and rev > 0, 'positive immutable revision id required')
    for endpoint, root in ROOTS.items():
        base = root + '/revisions/%04d' % rev
        require(package['endpoints'][endpoint]['source_root'] == base + '/source'
                and package['endpoints'][endpoint]['state_root'] == base + '/state-lora-development',
                'fixed campaign revision roots required')
    baseline, current = policy['baseline_source_files'], package['source_files']
    require(type(baseline) is dict and set(baseline) <= set(current), 'baseline source cannot be removed')
    require(all(current[name] == sha for name, sha in baseline.items() if name not in MUTABLE),
            'protected source changed; new owner approval required')
    for name in set(current) - set(baseline):
        path = Path(name)
        require(path.suffix == '.py' and path.parts[0] in {'training', 'plugin', 'agent', 'data_pipeline', 'tools'}
                and not path.is_absolute() and '..' not in path.parts, 'only reviewed public dependency additions allowed')
    expected = [('c1cfb2f13d0c56fb58e65481cc413189016ed8589428a6af869e27f76febf249',
                 '706cf374c8179e7c4adf2a462438ba37132cee250a4ba07b136b99cd6221df12', 2),
                ('aa280fb64ba123e4d7f999f5b5cd7db4302c2c3bb1337f2c459da938d408df9e',
                 '3e58e8d9df79c7d150a8f21522ba6e50869a5737ee20ce3840e8f3451d480f93', 1)]
    rows = policy['baseline_predecessors']
    require(type(rows) is list and len(rows) == 2, 'both consumed batches required')
    for row, (runtime, review_sha, count), suffix in zip(rows, expected, ('', '-r2')):
        require(row['prior_package_sha256'] == runtime and row['prior_review_sha256'] == review_sha
                and digest(row['prior_review']) == review_sha
                and row['prior_review']['load_attempts_consumed'] == count,
                'historical consumption/review cannot be rewritten')
        for endpoint, prefix in [('mac', '/Users/xiongweiluo/RhinoCoder/data'), ('gpu', '/data')]:
            base = prefix + '/lora-development-20261026' + suffix
            require(row['prior_endpoints'][endpoint]['source_root'] == base + '/source'
                    and row['prior_endpoints'][endpoint]['state_root'] == base + '/state-lora-development',
                    'historical endpoint cannot be replaced')
    return policy


def initialize(policy, approval, endpoint):
    """Explicit post-approval setup only. External sticky marker prevents reset."""
    require(approval == owner_record(policy) and policy['roots'] == ROOTS, 'direct campaign approval required')
    root = Path(ROOTS[endpoint]); marker = root.with_name(root.name + '.initialized')
    require(root.resolve() == root and not root.exists(), 'campaign must be new; no reset')
    fd = os.open(str(marker), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (digest(policy) + '\n').encode()); os.fsync(fd)
    finally: os.close(fd)
    root.mkdir(mode=0o700)
    publish_json(root, 'owner-approval.json', approval)
    publish_json(root, 'policy.json', policy)
    publish_json(root, 'campaign.lock', {'policy_sha256': digest(policy)})


class Campaign:
    def __init__(self, package, endpoint):
        self.package, self.endpoint = package, endpoint
        self.policy = validate(package); self.root = Path(ROOTS[endpoint])
        self.runtime = digest(package); self.rev = package['revision_id']
        os.close(private_directory(self.root))
        require(read_json(self.root, 'policy.json') == self.policy
                and read_json(self.root, 'owner-approval.json') == owner_record(self.policy)
                and read_json(self.root, 'campaign.lock') == {'policy_sha256': digest(self.policy)},
                'initialized approved campaign required; never initialize from a live entry')
        marker = self.root.with_name(self.root.name + '.initialized')
        fd = os.open(str(marker), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == 65
                    and os.read(fd, 66) == (digest(self.policy) + '\n').encode(), 'sticky campaign marker differs')
        finally: os.close(fd)

    @contextmanager
    def locked(self):
        fd = os.open(str(self.root / 'campaign.lock'), os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally: os.close(fd)

    def revision(self):
        row = read_json(self.root, 'revision-%04d.json' % self.rev)
        require(row['package_sha256'] == self.runtime and row['policy_sha256'] == digest(self.policy)
                and row['source_files'] == self.package['source_files']
                and row['endpoints'] == self.package['endpoints'], 'accepted exact revision required')
        return row

    def register(self, checks, source_root):
        """Delegated technical acceptance, never an owner approval substitute."""
        from .lora_development_admission import source_guard
        require(str(source_root) == self.package['endpoints'][self.endpoint]['source_root'], 'exact deployed endpoint source required')
        source_guard(source_root, self.package['source_files'])
        require(fragments(Path(source_root) / 'training/lora_development_loader.py') == self.policy['loader_fragments'],
                'inference body changed; outside startup repair authority')
        require(set(checks) == {'commit', 'ci_run_id', 'ci', 'cpu_evidence_sha256', 'reason',
            'repair_category', 'failed_load', 'failure_evidence_sha256', 'prior_mac_settlement',
            'semantic_change_review'}, 'complete revision checks required')
        require(type(checks['commit']) is str and len(checks['commit']) == 40
                and all(c in '0123456789abcdef' for c in checks['commit'])
                and type(checks['ci_run_id']) is int and checks['ci_run_id'] > 0
                and checks['ci'] == {n: 'success' for n in ('impact', 'python', 'ui', 'release', 'validate')}
                and type(checks['reason']) is str and bool(checks['reason'].strip())
                and checks['repair_category'] in {'initial', 'dependency', 'path', 'entry', 'startup_control'}
                and checks['semantic_change_review'] == 'no_research_contract_change', 'successful CI and scoped human-readable repair review required')
        require(type(checks['cpu_evidence_sha256']) is list and checks['cpu_evidence_sha256']
                and all(type(h) is str and len(h) == 64 and all(c in '0123456789abcdef' for c in h)
                        for h in checks['cpu_evidence_sha256']), 'CPU regression evidence required')
        with self.locked():
            publish_json(self.root, 'revision-%04d.json' % self.rev, {'package_sha256': self.runtime,
                'policy_sha256': digest(self.policy), 'revision_id': self.rev, 'checks': checks,
                'source_files': self.package['source_files'], 'endpoints': self.package['endpoints']})

    def begin_run(self):
        require(self.endpoint == 'mac', 'Mac run ownership required'); self.revision()
        with self.locked():
            require(not list(self.root.glob('slot-*.claim.json')), 'consumed slots cannot be restarted')
            for path in self.root.glob('run-*.claim.json'):
                prior = read_json(self.root, path.name)
                settled = read_json(self.root, 'run-%04d.settlement.json' % prior['revision_id'])
                require(settled['cleanup_verified'] and settled['slot_claims'] == 0, 'prior run unsettled or exposed; no startup retry')
            publish_json(self.root, 'run-%04d.claim.json' % self.rev, {'revision_id': self.rev, 'package_sha256': self.runtime})

    def claim_slot(self, slot):
        require(self.endpoint == 'mac' and slot in {'lora-dev-%02d' % n for n in range(32)}, 'fixed Mac slot required')
        with self.locked():
            require(read_json(self.root, 'run-%04d.claim.json' % self.rev)['package_sha256'] == self.runtime, 'run not claimed')
            publish_json(self.root, 'slot-' + slot + '.claim.json', {'package_sha256': self.runtime, 'slot_id': slot, 'revision_id': self.rev})

    def claim_load(self):
        require(self.endpoint == 'gpu', 'GPU loading ownership required'); revision = self.revision()
        with self.locked():
            names = sorted(p.name for p in self.root.glob('load-*.claim.json'))
            require(names == ['load-%d.claim.json' % n for n in range(4, 4 + len(names))] and len(names) < 2,
                    'cumulative maximum five loading attempts; never reset by revision')
            require(not (self.root / 'tasks-exposed.claim.json').exists(), 'exposed study cannot startup-retry')
            if names:
                last = read_json(self.root, names[-1]); number = last['global_load_number']
                stop = read_json(self.root, 'load-%d.settlement.json' % number)
                require(stop['status'] == 'gpu_stopped' and stop['tasks_exposed'] is False
                        and stop['stop']['exit_observed'] and stop['stop']['gpu_absence_verified'], 'prior loading cleanup unknown')
                prior = read_json(self.root, 'revision-%04d.json' % last['revision_id'])
                checks = revision['checks']
                require(last['package_sha256'] != self.runtime and revision['source_files'] != prior['source_files']
                        and checks['failed_load'] == number and checks['failure_evidence_sha256'] == digest(stop)
                        and checks['repair_category'] != 'initial', 'new failure evidence and targeted source repair required')
                mac = checks['prior_mac_settlement']
                require(type(mac) is dict and mac['package_sha256'] == last['package_sha256']
                        and mac['revision_id'] == last['revision_id'] and mac['cleanup_verified'] is True
                        and mac['slot_claims'] == 0 and mac['gpu_settlement_sha256'] == digest(stop),
                        'joint prior Mac/GPU cleanup and zero-slot evidence required')
            else:
                require(revision['checks']['failed_load'] is None and revision['checks']['prior_mac_settlement'] is None,
                        'initial campaign revision must retain the fixed audited predecessors')
            number = 4 + len(names)
            publish_json(self.root, 'load-%d.claim.json' % number, {'global_load_number': number,
                'revision_id': self.rev, 'package_sha256': self.runtime})
            return number

    def exposed(self):
        with self.locked():
            if not (self.root / 'tasks-exposed.claim.json').exists():
                publish_json(self.root, 'tasks-exposed.claim.json', {'revision_id': self.rev, 'package_sha256': self.runtime})

    def settle_load(self, number, settlement):
        with self.locked():
            require(read_json(self.root, 'load-%d.claim.json' % number)['package_sha256'] == self.runtime, 'loading claim differs')
            publish_json(self.root, 'load-%d.settlement.json' % number, settlement)

    def settle_run(self, result):
        with self.locked():
            host, gpu, key = result.get('host') or {}, result.get('gpu') or {}, result.get('key_removal') or {}
            gpu_clean = (result.get('gpu_launch_attempted') is False and not gpu) or (
                gpu.get('status') == 'gpu_stopped' and (gpu.get('stop') or {}).get('exit_observed') is True
                and (gpu.get('stop') or {}).get('gpu_absence_verified') is True)
            clean = (host.get('status') == 'host_stopped' and host.get('exact_delegate_remove_returned') is True
                     and key.get('actual_absence_checked') is True and gpu_clean)
            publish_json(self.root, 'run-%04d.settlement.json' % self.rev, {'revision_id': self.rev,
                'package_sha256': self.runtime, 'result_sha256': digest(result), 'cleanup_verified': clean,
                'gpu_settlement_sha256': digest(gpu),
                'slot_claims': len(list(self.root.glob('slot-*.claim.json'))), 'elapsed_seconds': result['elapsed_seconds']})

    def retired(self):
        rows = list(self.policy['baseline_predecessors'])
        for path in self.root.glob('run-*.settlement.json'):
            row = read_json(self.root, path.name)
            if row['revision_id'] == self.rev: continue
            require(row['cleanup_verified'] and row['slot_claims'] == 0, 'previous run cannot be replaced')
            prior = read_json(self.root, 'revision-%04d.json' % row['revision_id'])
            rows.append({'prior_package_sha256': prior['package_sha256'], 'prior_endpoints': prior['endpoints']})
        return rows
