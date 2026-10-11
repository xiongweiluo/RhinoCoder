"""Owned-child qualification and one predeclared stop; no process launch.

An independently frozen supervisor pins its exact newly created child before
loading starts. Parent ownership is mandatory, not a PID supplied by a model.
Source/runtime approval must separately predeclare this precise policy.
"""
from training.c5_reuse_evidence import canonical, require, sha, strict
from training.c5_reuse_field_scope import validate_binding
from training.c5_reuse_stop import target

POLICY={'kind':'one_new_owned_child_pidfd_only','qualify_before_model_loading':True,
        'signal':'SIGTERM','signals_max':1,'exit_wait_seconds':30,'name_kill_allowed':False,
        'reconnect_or_retry_allowed':False,'signal_escalation_allowed':False}


class OwnedChildStop:
    def __init__(self,binding,policy,parent_pid,child_pid,ops,journal,registry):
        validate_binding(binding)
        require(binding['endpoint']=='gpu' and policy==POLICY and registry.binding==binding,'reuse_owned_stop_scope')
        require(type(parent_pid) is int and parent_pid>1 and type(child_pid) is int and child_pid>1
                and parent_pid!=child_pid,'reuse_owned_child_ids')
        ops.guard()
        self.fd=ops.pin(child_pid)
        self.ops,self.journal,self.registry=ops,journal,registry
        try:
            expected=ops.identity(child_pid); target(expected)
            require(ops.parent(child_pid)==parent_pid and not ops.exited(self.fd),'reuse_child_not_owned_or_exited')
            self.expected=strict(canonical(expected)); self.parent_pid=parent_pid; self.spent=False
            journal('owned_child_qualified',{'target':self.expected,'parent_pid':parent_pid,'policy_sha256':sha(policy),
                                           'model_loading_started':False})
        except BaseException:
            ops.close(self.fd); self.fd=None; raise

    def stop(self):
        require(self.fd is not None and not self.spent,'reuse_owned_stop_no_retry')
        self.spent=True
        value={'signal_attempts':0,'exit_observed':False,'gpu_release_verified':None,'status':'unknown_no_retry'}
        try:
            self.ops.guard()
            self.registry.claim('stop')
            if self.ops.exited(self.fd):
                value.update(exit_observed=True,status='already_exited_no_signal')
                return value
            require(self.ops.identity(self.expected['pid'])==self.expected
                    and self.ops.parent(self.expected['pid'])==self.parent_pid,'reuse_owned_target_drift')
            self.journal('owned_signal_intent',{'target_sha256':sha(self.expected),'signal':'SIGTERM','attempts_max':1})
            self.ops.guard()
            require(self.ops.identity(self.expected['pid'])==self.expected
                    and self.ops.parent(self.expected['pid'])==self.parent_pid,'reuse_owned_target_after_intent')
            value['signal_attempts']=1
            self.ops.send(self.fd)
            exited=self.ops.wait(self.fd,30)
            require(type(exited) is bool,'reuse_owned_exit_observation')
            value.update(exit_observed=exited,status='exit_observed_pending_gpu' if exited else 'unknown_no_retry')
            return value
        finally:
            self.journal('owned_stop_result',value)

    def close(self):
        if self.fd is not None: self.ops.close(self.fd); self.fd=None
