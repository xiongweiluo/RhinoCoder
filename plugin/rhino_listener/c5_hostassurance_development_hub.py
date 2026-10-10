"""New research-only host-aware hub; no registration or live effects on import."""
import json

from .c5_modelbridge_hub import DevelopmentHub
from .c5_research_session import IdleBridge
from .c5_research_channel import publish_json
from .c5_research_native import digest, require


class CleanupAwareBridge(IdleBridge):
    def __init__(self, *args, cleanup_source, assurance, **kwargs):
        self.cleanup_source, self.assurance, self.current_request = cleanup_source, assurance, None
        super().__init__(*args, **kwargs)

    def _attest(self, request):
        publish_json(self.directory,'host-check-%04d.json'%self.seq,{
            'request_sha256':digest(request),'host_record_sha256':self.assurance.head,
            'host_sequence':self.assurance.sequence-1,'runtime_freeze_sha256':self.gate.owner_freeze})

    def _source(self):
        super()._source()
        if self.current_request is not None: self._attest(self.current_request)

    def handle(self, request):
        # The original handler still validates exact HMAC/scope/TTL and owns
        # close/stop. This choice NEVER admits execute/capture under cleanup.
        p = request.get('envelope',{}).get('payload',{}) if isinstance(request,dict) else {}
        cleanup = isinstance(p,dict) and request.get('kind') == 'control' and p.get('action') in {'close','stop'}
        original = self.guard_source
        if cleanup: self.guard_source = self.cleanup_source
        self.current_request = request
        try: return super().handle(request)
        finally: self.guard_source, self.current_request = original, None


class HostAwareDevelopmentHub(DevelopmentHub):
    def __init__(self, *args, byte_guard, **kwargs):
        self.byte_guard, self.assurance, self.preparing, self.cleanup_mode = byte_guard, None, True, False
        self.current_request, self.request_attested = None, False
        def bridge(*a, **kw): return CleanupAwareBridge(*a, cleanup_source=self.cleanup_guard, assurance=self.assurance, **kw)
        kwargs['source'], kwargs['bridge_factory'] = self.dispatch_guard, bridge
        super().__init__(*args, **kwargs)

    def dispatch_guard(self):
        if self.preparing: return self.byte_guard()
        require(self.assurance is not None, 'new sealed host assurance required')
        return self.assurance.checkpoint('dispatch-%04d' % self.assurance.checkpoints)

    def cleanup_guard(self):
        require(not self.preparing and self.assurance is not None, 'cleanup without started new host scope')
        return self.assurance.cleanup_checkpoint('cleanup-%04d' % self.assurance.checkpoints)

    def guard(self):
        source = self.source
        if self.cleanup_mode: self.source = self.cleanup_guard
        try:
            result=super().guard()
            if self.current_request is not None and not self.request_attested:
                publish_json(self.state,'hub-host-check-%04d.json'%self.seq,{
                    'request_sha256':digest(self.current_request),'host_record_sha256':self.assurance.head,
                    'host_sequence':self.assurance.sequence-1,'runtime_freeze_sha256':digest(self.freeze)})
                self.request_attested=True
            return result
        finally: self.source = source

    def handle(self, envelope):
        require(not self.preparing and self.assurance is not None and self.assurance.baseline is not None,
            'hub not sealed; no opening/dispatch')
        payload = envelope.get('payload',{}) if isinstance(envelope,dict) else {}
        self.cleanup_mode = isinstance(payload,dict) and payload.get('action') == 'stop'
        self.current_request, self.request_attested = envelope, False
        try:
            value = super().handle(envelope)
            if value.get('status') == 'hub_stopped':
                receipt = self.assurance.finish()
                publish_json(self.state,'host-continuity-terminal-receipt.json',receipt)
                # Independently capture this terminal SHA, not a SHA invented
                # by rereading the producer's seal during audit.
                print('C5_HOST_CONTINUITY_EXTERNAL_RECEIPT '+json.dumps(receipt,sort_keys=True))
            return value
        finally: self.cleanup_mode, self.current_request = False, None
