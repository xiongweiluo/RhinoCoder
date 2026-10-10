"""New formal-only finite journal. No host effects on import/constructor.

Underlying raw observer, source checks and fail-closed comparison are retained.
Old sessions/registry/bounds are not changed. Capacity cannot authorize tools.
"""
from .c5_host_assurance_session import HostAssuranceSession
from .c5_host_assurance_v2 import compare_visible_continuity
from .c5_research_native import digest, require
from .c5_research_channel import publish_json
from .c5_formal20_observation_capacity import ObservationCapacity, LIMITS
from .c5_formal20_policy_v2 import STUDY_ID
import math


class FormalHostSession(HostAssuranceSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        require(self.binding.get('formal_capacity_verified') is True
            and self.binding.get('study_id') == STUDY_ID, 'new validated formal capacity binding required')
        self.quota = ObservationCapacity(LIMITS)

    def _write(self, kind, payload):
        require(not self.finished, 'formal host journal sealed')
        elapsed = self.clock()-self.start_time
        require(math.isfinite(elapsed) and elapsed >= 0, 'formal host monotonic clock invalid')
        self.quota.admit_record(kind)
        value = {'schema_version':1,'study_id':self.binding['study_id'],'policy_id':self.binding['policy_id'],
            'runtime_freeze_sha256':self.binding['runtime_freeze_sha256'],'sequence':self.sequence,
            'elapsed_seconds':elapsed,'previous_sha256':self.head,'kind':kind,'payload':payload}
        value['record_sha256']=digest(value)
        publish_json(self.state,'host-continuity-%04d.json'%self.sequence,value)
        self.head,self.sequence=value['record_sha256'],self.sequence+1

    def _checkpoint(self, label, *, cleanup):
        require(isinstance(label,str) and label.isascii() and 0<len(label)<=80
            and all(c.isalnum() or c in '-_.' for c in label), 'bounded formal checkpoint label required')
        kind='cleanup_checkpoint' if cleanup else 'checkpoint'
        used,cap=(self.quota.cleanup,LIMITS['cleanup_checkpoints']) if cleanup else (self.quota.normal,LIMITS['normal_checkpoints'])
        if used >= cap or (not cleanup and self.quota.dispatch_blocked):
            self.blocked=True; self.quota.dispatch_blocked=True
            raise RuntimeError('formal checkpoint quota exhausted; no dispatch/retry')
        self.checkpoints += 1
        try:
            self._source()
            raw = self._capture()
            error=None
            try:
                require(self.baseline is not None,'formal baseline never sealed')
                compare_visible_continuity(self.baseline,raw['snapshot'],raw['events'])
            except BaseException as exc:
                self.blocked,error=True,type(exc).__name__
            self._write(kind,{'label':label,**raw,'continuity_error_type':error,'source_inventory_sha256':self.source_sha})
            if error is not None and not cleanup: raise RuntimeError('formal host drift; no dispatch/retry')
            return self.source_sha
        except BaseException as exc:
            self.blocked=True
            self._write('failure',{'phase':'cleanup' if cleanup else 'checkpoint','error_type':type(exc).__name__})
            raise
