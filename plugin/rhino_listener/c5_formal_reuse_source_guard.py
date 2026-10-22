"""Complete registered Python/JSON/requirements byte guard, Rhino 3.9 safe.

The original research guard accepts a smaller historical manifest. Use the
already validated recovery guard for the new closed public-source inventory;
neither legacy guard nor its deployed bytes are changed.
"""
from .c5_recovery_runtime_scope import SourceGuard as RecoverySourceGuard
from .c5_research_native import digest,require

class SourceGuard:
    def __init__(self,root,files,expected_inventory_sha256,*,project_prefixes=()):
        require(digest(files)==expected_inventory_sha256,'formal_reuse_source_inventory_binding')
        self.expected=expected_inventory_sha256
        self.inner=RecoverySourceGuard(root,files,private_prefixes=tuple(project_prefixes))
    def __call__(self):
        value=self.inner()
        require(value==self.expected,'formal_reuse_source_inventory_drift')
        return value
