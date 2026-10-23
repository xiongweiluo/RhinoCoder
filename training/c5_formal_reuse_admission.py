"""Same global admission root, preserved nonempty history, finite formal attempts.

Import and guard are read-only. Initialization/start require the NEW exact
formal grant. A pre-exposure failure never erases its attempt, clocks or keys.
"""
import hashlib
import os
from pathlib import Path
from training.c5_reuse_evidence import canonical,sha,require,strict,exact,is_sha
from training.c5_recovery_storage import EvidenceLog,read_private,write_once,directory
import math
import time
from training.c5_recovery_policy import validate_scope,require_grant,retry_decision
from training.c5_recovery_confirmation import validate_receipt
from training.c5_recovery_policy import POLICY
from plugin.rhino_listener.c5_formal_reuse_scope import STUDY_ID,authority,MAC_STATE,REMOTE_STATE,PACKAGE_LAYOUT

NAMESPACE='formal-reuse-v1'
HISTORY_FILE='eval/c5/formal-reuse-history-20261022.json'
ROOTS={'mac':Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/c5-reuse-global-admission-v1'),
    'gpu':Path('/data/c5-reuse-global-admission-v1')}

def campaign_scope(spec,freeze):
    from plugin.rhino_listener.c5_research_native import digest
    return {'campaign_id':STUDY_ID,'phase':'formal','spec_sha256':digest(spec),'runtime_sha256':digest(freeze),
        'policy_sha256':sha(POLICY),'history_sha256':freeze['history_sha256'],
        'public_plan_sha256':spec['public_commitment_sha256'],'contract_sha256':sha(spec['comparison']),
        'development_seconds_max':spec.get('run_package',{}).get('policy',{}).get('gpu_residency_seconds_max',64800),'generation_cutoff_epoch':spec['model_generation_cutoff_epoch']}

def history_guard(endpoint,history,*,root=None):
    require(endpoint in ROOTS and type(history) is dict,'formal_reuse_history_endpoint')
    root=ROOTS[endpoint] if root is None else Path(root)
    require(root.is_absolute() and root.resolve()==root and root.name=='c5-reuse-global-admission-v1',
        'formal_reuse_same_global_root')
    document=history['endpoints'][endpoint]
    require(type(document) is dict and set(document)=={'global_files','retired_files','global_top_level'}
        and document['global_files'] and document['retired_files'],'formal_reuse_nonempty_history_required')
    retired=history['retired_instances']
    require(retired==['reuse-dev-20261011-a','reuse-dev-20261012-b',
        'reuse-dev-20261012-c','reuse-dev-20261012-d'],'formal_reuse_exact_retired_instances')
    expected_retired={name+'-state/'+suffix for name in retired for suffix in
        ('entry-retired-no-retry.json','owner-approval.retired-no-retry.json')}
    require(set(document['retired_files'])==expected_retired
        and all(type(h) is str and is_sha(h) for h in document['retired_files'].values()),
        'formal_reuse_exact_retired_paths')
    require(all(type(n) is str and not Path(n).is_absolute() and '..' not in Path(n).parts
        and NAMESPACE not in Path(n).parts and is_sha(h) for n,h in document['global_files'].items()),
        'formal_reuse_closed_history_paths')
    require(type(document['global_top_level']) is list and len(set(document['global_top_level']))==len(document['global_top_level'])
        and set(document['global_top_level'])=={Path(n).parts[0] for n in document['global_files']},
        'formal_reuse_history_top_level_coverage')
    names=set(document['global_top_level'])
    require('engineering-recovery-v3' in names and NAMESPACE not in names,'formal_reuse_completed_development_required')
    def guard():
        directory(root)
        require(set(os.listdir(root)) in (names,names|{NAMESPACE}),'formal_reuse_unknown_admission_population')
        actual={p.relative_to(root).as_posix() for p in root.rglob('*')
            if NAMESPACE not in p.relative_to(root).parts and (p.is_file() or p.is_symlink())}
        require(actual==set(document['global_files']),'formal_reuse_old_admission_population_changed')
        require(all(hashlib.sha256(read_private(root/n,empty=h==hashlib.sha256(b'').hexdigest())).hexdigest()==h
            for n,h in document['global_files'].items()),'formal_reuse_old_admission_bytes_changed')
        for name,h in document['retired_files'].items():
            p=root.parent/name
            require(not p.is_symlink() and p.resolve()==p
                and hashlib.sha256(read_private(p)).hexdigest()==h,'formal_reuse_retired_history_changed')
        for name in history['retired_instances']:
            require(not os.path.lexists(root.parent/(name+'-state')/'owner-approval.json'),
                'formal_reuse_retired_grant_restored')
    guard();return guard

def attempt_state(endpoint,attempt):
    require(endpoint in ('mac','gpu') and type(attempt) is int and 1<=attempt<=(5 if PACKAGE_LAYOUT is not None else 3),
        'formal_reuse_bounded_preexposure_attempt')
    return (MAC_STATE if endpoint=='mac' else REMOTE_STATE)/('preload-'+str(attempt))

def open_formal_campaign(spec,freeze,grant,history,*,create=False,root=None,wall=None):
    authority(spec,freeze,grant,check_time=create)
    require(sha(history)==freeze['history_sha256'],'formal_reuse_history_binding')
    root=ROOTS['mac'] if root is None else Path(root);guard=history_guard('mac',history,root=root)
    parent=root/NAMESPACE
    require(not create or freeze.get('incremental_revision') is None,'formal_reuse_revision_cannot_create_new_campaign')
    if create:
        require(not parent.exists(),'formal_reuse_campaign_already_exists');parent.mkdir(mode=0o700)
        write_once(parent,'campaign.json',{'campaign_id':STUDY_ID,'history_sha256':sha(history),
            'initial_scope_sha256':sha(campaign_scope(spec,freeze))})
    directory(parent);manifest=strict(read_private(parent/'campaign.json'))
    scope=campaign_scope(spec,freeze)
    from training.c5_formal_reuse_revision import initial_scope
    initial=initial_scope(spec,freeze)
    require(manifest=={'campaign_id':STUDY_ID,'history_sha256':sha(history),'initial_scope_sha256':sha(initial)},
        'formal_reuse_no_replacement_campaign')
    log=EvidenceLog(parent/'ledger',initial,guard,create=create)
    return FormalCampaign(scope,log,**({'wall':wall} if wall is not None else {}))

def require_startable(campaign,attempt):
    value=campaign.observation()
    if value.get('package') is not None:
        require(value['attempts']==value['package_start_attempt'] or value['attempts'] in value['settled_attempts'],
            'run_package_previous_gpu_usage_unsettled')
    require(value['attempts']+1==attempt and value['attempts']<value.get('attempts_max',3) and value['formal_consumed'] is False
        and value['active'] is False and value['status'] in ('WAITING_OWNER','PREPARED',
            'RETRYABLE_ENGINEERING','RETRYABLE_ENGINEERING_DIAGNOSTICS_INCOMPLETE'),
        'formal_reuse_attempt_requires_known_pause_and_no_private_consumption')
    return value

def consume_before_private(campaign,attempt,state):
    value=campaign.observation()
    require(value['attempts']==attempt and value['active'] and value['ready'] and not value['formal_consumed'],
        'formal_reuse_private_claim_order')
    anchor={'attempt':attempt,'state_root':str(state),'campaign_head_sha256':campaign.log.rows()[-1]['record_sha256']}
    # EvidenceLog append fsyncs before the owner-controlled private loader runs.
    campaign.expose_private(sha(anchor))
    return anchor


def formal_replay(scope, rows):
    validate_scope(scope)
    state = {'attempts': 0, 'active': False, 'formal_consumed': False, 'first_load_epoch': None, 'last_epoch': None, 'status': 'WAITING_OWNER', 'receipt': None, 'ready': False, 'begun': False, 'scope': dict(scope), 'attempts_max':3, 'package':None, 'load_intent_epoch':None}
    for row in rows:
        scope = state['scope']
        kind, p = (row['kind'], row['payload'])
        if kind in ('package_owner_session_confirmed','package_owner_custody_consent','package_preload_observed','gpu_residency_settled'):
            from training.c5_formal_run_package import replay_package_event
            replay_package_event(state,kind,p);continue
        if kind=='run_package_revision_accepted':
            from training.c5_formal_run_package import replay_package_revision
            replay_package_revision(state,row);continue
        if kind in ('runtime_revision_accepted', 'resource_runtime_revision_accepted'):
            exact(p, ('scope', 'grant', 'previous_head_sha256') + (('resource_amendment',) if kind == 'resource_runtime_revision_accepted' else ()))
            revised = validate_scope(p['scope'])
            require(not state['active'] and (not state['formal_consumed']) and (state['status'] not in ('PAUSED_RECONCILIATION', 'AWAITING_INDEPENDENT_AUDIT')) and (state['attempts'] < state['attempts_max']), 'recovery_revision_requires_known_pause')
            require(all((revised[k] == scope[k] for k in ('campaign_id', 'phase', 'policy_sha256', 'history_sha256', 'public_plan_sha256', 'contract_sha256'))), 'recovery_revision_cannot_change_contract_or_reset_budget')
            if kind == 'resource_runtime_revision_accepted':
                amendment = {'old_seconds_max': scope['development_seconds_max'], 'new_seconds_max': revised['development_seconds_max'], 'first_load_epoch': state['first_load_epoch'], 'attempts': state['attempts'], 'budget_reset': False, 'old_budget_recredited': False}
                require(p['resource_amendment'] == amendment and scope['phase'] == 'public_engineering' and (revised['development_seconds_max'] > scope['development_seconds_max']), 'recovery_explicit_resource_amendment_required')
            else:
                require(revised['development_seconds_max'] == scope['development_seconds_max'], 'recovery_revision_cannot_change_contract_or_reset_budget')
            require(revised['generation_cutoff_epoch'] >= scope['generation_cutoff_epoch'] and revised != scope, 'recovery_revision_not_new_material')
            grant = dict(p['grant'])
            require(grant.pop('previous_campaign_head_sha256', None) == p['previous_head_sha256'] and row.get('previous_sha256', p['previous_head_sha256']) == p['previous_head_sha256'], 'recovery_revision_requires_prior_raw_head')
            require_grant(revised, grant)
            state.update(scope=dict(revised), receipt=None, status='WAITING_OWNER')
        elif kind == 'owner_preload_confirmed':
            require(not state['active'] and not state['formal_consumed'] and (state['receipt'] is None or (scope['phase']=='formal' and state['status'] in ('RETRYABLE_ENGINEERING','RETRYABLE_ENGINEERING_DIAGNOSTICS_INCOMPLETE'))), 'recovery_confirmation_order')
            validate_receipt(scope, p['snapshot'], p['receipt'])
            state['receipt'] = p
            state['status'] = 'PREPARED'
        elif kind == 'owner_resume_requested':
            exact(p, ('attempts',))
            require(state['status'] == 'PAUSED_OWNER' and (not state['active']) and (not state['formal_consumed']) and (p['attempts'] == state['attempts']) and (state['attempts'] < state['attempts_max']), 'recovery_owner_resume_order')
            state['status'] = 'RETRYABLE_ENGINEERING'
        elif kind == 'attempt_load_intent':
            exact(p, ('attempt', 'epoch'))
            require((state['package'] is None or (state['package_owner_consent'] and state['package_preload_attempt']==p['attempt'] and state['attempts']-state['package_start_attempt'] < state['package']['policy']['package_preexposure_loads_max'])) and state['receipt'] is not None and (not state['active']) and (not state['formal_consumed']) and (state['status'] in ('PREPARED', 'RETRYABLE_ENGINEERING', 'RETRYABLE_ENGINEERING_DIAGNOSTICS_INCOMPLETE')) and (type(p['attempt']) is int) and (p['attempt'] == state['attempts'] + 1) and (p['attempt'] <= state['attempts_max']), 'recovery_attempt_order')
            require(type(p['epoch']) in (int, float) and math.isfinite(p['epoch']) and (p['epoch'] > 0) and (state['last_epoch'] is None or p['epoch'] >= state['last_epoch']), 'recovery_clock_regression')
            if state['first_load_epoch'] is None:
                require(p['epoch'] + scope['development_seconds_max'] <= scope['generation_cutoff_epoch'], 'recovery_complete_window_unavailable')
                state['first_load_epoch'] = p['epoch']
            require(state['package'] is not None or p['epoch'] < min(state['first_load_epoch'] + scope['development_seconds_max'] - 60, scope['generation_cutoff_epoch'] - 60), 'recovery_shared_budget_exhausted')
            state.update(attempts=p['attempt'], active=True, ready=False, begun=False, status='LOADING', last_epoch=p['epoch'],load_intent_epoch=p['epoch'])
        elif kind == 'budget_observation':
            exact(p, ('epoch',))
            require(state['first_load_epoch'] is not None and type(p['epoch']) in (int, float) and math.isfinite(p['epoch']) and (p['epoch'] >= state['last_epoch']) and (state['package'] is not None or p['epoch'] < min(state['first_load_epoch'] + scope['development_seconds_max'] - 60, scope['generation_cutoff_epoch'] - 60)), 'recovery_shared_budget_exhausted')
            state['last_epoch'] = p['epoch']
        elif kind == 'worker_ready':
            exact(p, ('attempt', 'raw_anchor_sha256'))
            require(state['active'] and (not state['ready']) and (p['attempt'] == state['attempts']) and is_sha(p['raw_anchor_sha256']), 'recovery_ready_order')
            state.update(ready=True, status='READY')
        elif kind in ('generation_begin_intent', 'private_exposure_intent'):
            exact(p, ('attempt', 'raw_anchor_sha256'))
            require(state['active'] and p['attempt'] == state['attempts'] and is_sha(p['raw_anchor_sha256']), 'recovery_consumption_order')
            if kind == 'generation_begin_intent':
                require(state['ready'] and (not state['begun']), 'recovery_generation_order')
                state['begun'] = True
            else:
                require(scope['phase'] == 'formal' and (not state['formal_consumed']), 'recovery_private_exposure_once')
            if scope['phase'] == 'formal':
                state['formal_consumed'] = True
            state['status'] = 'RUNNING'
        elif kind == 'attempt_failed':
            exact(p, ('attempt', 'error', 'proof', 'decision'))
            require(state['active'] and p['attempt'] == state['attempts'], 'recovery_failure_order')
            decision = formal_retry_decision(state, p['error'], p['proof'])
            require(decision == p['decision'], 'recovery_failure_decision_changed')
            state.update(active=False, status=decision)
        elif kind == 'cleanup_reconciled':
            exact(p, ('error', 'proof', 'decision'))
            require(not state['active'] and state['status'] == 'PAUSED_RECONCILIATION', 'recovery_reconciliation_order')
            decision = formal_retry_decision(state, p['error'], p['proof'])
            require(p['decision'] == decision and decision != 'PAUSED_RECONCILIATION', 'recovery_reconciliation_incomplete')
            state['status'] = decision
        elif kind == 'attempt_completed':
            exact(p, ('attempt', 'raw_anchor_sha256'))
            require(state['active'] and state['begun'] and (p['attempt'] == state['attempts']) and is_sha(p['raw_anchor_sha256']), 'recovery_completion_order')
            state.update(active=False, status='AWAITING_INDEPENDENT_AUDIT')
        else:
            raise ValueError('recovery_unknown_event')
    return state

def formal_retry_decision(state,error,proof):
    if state.get('package') is None:
        return retry_decision(state['scope'],state['attempts'],state['formal_consumed'],error,proof)
    # Validate the same closed original evidence shape; only the finite limit is
    # changed prospectively by the exact package grant in this same ledger.
    decision=retry_decision(state['scope'],min(state['attempts'],3),state['formal_consumed'],error,proof)
    if decision=='ATTEMPT_LIMIT_REACHED':
        from plugin.rhino_listener.c5_run_package_policy import retry_authorized
        p=state['package']
        if retry_authorized(p['policy'],package_start_attempt=p['timing_migration']['prior_attempts_consumed'],
                attempts=state['attempts'],exposed=state['formal_consumed'],same_pair=True,
                complete_proof=all(proof[k] for k in proof if k!='raw_anchor_sha256')):
            return 'RETRYABLE_ENGINEERING'
    return decision


class FormalCampaign:

    def __init__(self, scope, log, *, wall=time.time):
        validate_scope(scope)
        self.initial_scope, self.log, self.wall = (log.binding, log, wall)
        require(self.observation()['scope'] == scope, 'recovery_campaign_log_binding')

    @property
    def scope(self):
        return self.observation()['scope']

    def observation(self):
        with self.log.locked():
            return formal_replay(self.initial_scope, self.log.rows())

    def _event(self, kind, payload):
        with self.log.locked():
            formal_replay(self.initial_scope, self.log.rows() + [{'kind': kind, 'payload': payload, 'previous_sha256': self.log.rows()[-1]['record_sha256'] if self.log.rows() else '0' * 64}])
            return self.log.append_locked(kind, payload)

    def accept_revision(self, scope, grant):
        with self.log.locked():
            rows = self.log.rows()
            head = rows[-1]['record_sha256'] if rows else '0' * 64
            payload = {'scope': scope, 'grant': grant, 'previous_head_sha256': head}
            formal_replay(self.initial_scope, rows + [{'kind': 'runtime_revision_accepted', 'payload': payload, 'previous_sha256': head}])
            return self.log.append_locked('runtime_revision_accepted', payload)

    def accept_resource_revision(self, scope, grant):
        with self.log.locked():
            rows = self.log.rows()
            state = formal_replay(self.initial_scope, rows)
            head = rows[-1]['record_sha256'] if rows else '0' * 64
            payload = {'scope': scope, 'grant': grant, 'previous_head_sha256': head, 'resource_amendment': {'old_seconds_max': state['scope']['development_seconds_max'], 'new_seconds_max': scope['development_seconds_max'], 'first_load_epoch': state['first_load_epoch'], 'attempts': state['attempts'], 'budget_reset': False, 'old_budget_recredited': False}}
            formal_replay(self.initial_scope, rows + [{'kind': 'resource_runtime_revision_accepted', 'payload': payload, 'previous_sha256': head}])
            return self.log.append_locked('resource_runtime_revision_accepted', payload)

    def confirm(self, snap, receipt):
        return self._event('owner_preload_confirmed', {'snapshot': snap, 'receipt': receipt})

    def resume_after_owner_pause(self):
        self.budget()
        return self._event('owner_resume_requested', {'attempts': self.observation()['attempts']})

    def start(self):
        state = self.observation()
        self._event('attempt_load_intent', {'attempt': state['attempts'] + 1, 'epoch': self.wall()})
        return self.observation()['attempts']

    def budget(self):
        state = self.observation()
        now = self.wall()
        require(type(now) in (int, float) and math.isfinite(now), 'recovery_budget_clock')
        if state['first_load_epoch'] is None:
            return self.scope['development_seconds_max'] - 60
        require(now >= state['last_epoch'], 'recovery_clock_regression')
        if state.get('package') is not None:
            from training.c5_formal_run_budget import require_recovery_window
            value=require_recovery_window(state['package'],state,now=now)
            self._event('budget_observation',{'epoch':now})
            return min(value['remaining_budget_seconds'],value['remaining_lease_seconds'])
        remaining = min(state['first_load_epoch'] + self.scope['development_seconds_max'] - 60, self.scope['generation_cutoff_epoch'] - 60) - now
        require(remaining > 0, 'recovery_shared_budget_exhausted')
        self._event('budget_observation', {'epoch': now})
        return remaining

    def ready(self, anchor):
        return self._event('worker_ready', {'attempt': self.observation()['attempts'], 'raw_anchor_sha256': anchor})

    def begin(self, anchor):
        return self._event('generation_begin_intent', {'attempt': self.observation()['attempts'], 'raw_anchor_sha256': anchor})

    def expose_private(self, anchor):
        return self._event('private_exposure_intent', {'attempt': self.observation()['attempts'], 'raw_anchor_sha256': anchor})

    def failed(self, error, proof):
        state = self.observation()
        decision = formal_retry_decision(state, error, proof)
        self._event('attempt_failed', {'attempt': state['attempts'], 'error': error, 'proof': proof, 'decision': decision})
        return decision

    def reconcile(self, error, proof):
        state = self.observation()
        decision = formal_retry_decision(state, error, proof)
        self._event('cleanup_reconciled', {'error': error, 'proof': proof, 'decision': decision})
        return decision

    def completed(self, anchor):
        return self._event('attempt_completed', {'attempt': self.observation()['attempts'], 'raw_anchor_sha256': anchor})
