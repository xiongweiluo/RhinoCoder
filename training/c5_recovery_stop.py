"""One shared pidfd stop result per exact qualified target, across actors."""
from training.c5_reuse_evidence import canonical,exact,require,sha,strict
from training.c5_reuse_stop import target
from training.c5_recovery_storage import EvidenceLog

class CoordinatedStop:
    def __init__(self,log,qualification):
        require(isinstance(log,EvidenceLog),'recovery_stop_log')
        exact(qualification,('target','parent_pid','model_loading_started'))
        target(qualification['target'])
        require(type(qualification['parent_pid']) is int and qualification['parent_pid']>1
                and qualification['parent_pid']!=qualification['target']['pid']
                and qualification['model_loading_started'] is False,
                'recovery_original_preload_qualification')
        require(log.binding.get('qualification_sha256')==sha(qualification),'recovery_stop_target_binding')
        self.log=log;self.q=strict(canonical(qualification))

    def observe(self):
        with self.log.locked():
            rows=self.log.rows()
            return self._observed(rows)

    def _observed(self,rows):
        kinds=[r['kind'] for r in rows]
        require(kinds in ([],['stop_claim'],['stop_claim','stop_result']),
                'recovery_stop_event_order')
        if not rows:return {'status':'not_requested','retry_signal_allowed':False}
        require(rows[0]['payload']=={'qualification_sha256':sha(self.q),'signals_max':1},
                'recovery_stop_claim_changed')
        if len(rows)==1:return {'status':'unknown_after_claim','retry_signal_allowed':False}
        value=rows[1]['payload'];exact(value,('status','signal_attempts','exit_observed','error_type'))
        require(value['status'] in ('already_exited','exit_observed','unknown')
                and type(value['signal_attempts']) is int and value['signal_attempts'] in (0,1)
                and type(value['exit_observed']) is bool
                and (value['error_type'] is None or type(value['error_type']) is str),
                'recovery_stop_result')
        require((value['status']=='unknown' and value['exit_observed'] is False)
                or (value['status']=='already_exited' and value['signal_attempts']==0
                    and value['exit_observed'] is True and value['error_type'] is None)
                or (value['status']=='exit_observed' and value['signal_attempts']==1
                    and value['exit_observed'] is True and value['error_type'] is None),
                'recovery_stop_result_semantics')
        return dict(value,retry_signal_allowed=False)

    def stop(self,ops):
        # Both independent entry and supervisor use THIS GPU-local log.
        # Waiters read the first result; they never claim or signal again.
        with self.log.locked():
            rows=self.log.rows()
            if rows:return self._observed(rows)
            ops.guard();fd=ops.pin(self.q['target']['pid'])
            value={'status':'unknown','signal_attempts':0,'exit_observed':False,'error_type':None}
            try:
                if not ops.exited(fd):
                    require(ops.identity(self.q['target']['pid'])==self.q['target']
                            and ops.parent(self.q['target']['pid'])==self.q['parent_pid'],
                            'recovery_stop_identity_drift')
                self.log.append_locked('stop_claim',{'qualification_sha256':sha(self.q),'signals_max':1})
                if ops.exited(fd):
                    value.update(status='already_exited',exit_observed=True)
                else:
                    ops.guard()
                    require(ops.identity(self.q['target']['pid'])==self.q['target']
                            and ops.parent(self.q['target']['pid'])==self.q['parent_pid'],
                            'recovery_stop_identity_after_claim')
                    value['signal_attempts']=1;ops.send(fd)
                    exited=ops.wait(fd,30);require(type(exited) is bool,'recovery_stop_exit_observation')
                    value.update(exit_observed=exited,status='exit_observed' if exited else 'unknown')
            except BaseException as error:
                value['error_type']=type(error).__name__
                # A pin/identity rejection BEFORE claim permits no signal.
                # Once claimed, even a crash cannot make another actor resend.
                if self.log.rows():self.log.append_locked('stop_result',value)
                raise
            else:
                self.log.append_locked('stop_result',value)
                return dict(value,retry_signal_allowed=False)
            finally:ops.close(fd)
