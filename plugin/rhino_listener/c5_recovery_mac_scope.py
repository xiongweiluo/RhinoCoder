"""Actual readable Mac checks reused; new fixed freeze and grant only."""
from .c5_recovery_runtime_scope import approved_entry
from .c5_followup_mac_scope import readable_scope,verify_audit_tokenizer
from .c5_recovery_profile import MAC_FLAGS
def mac_scope(root,attempt,*,embedded=False,private_prefixes=(),cleanup_only=False):
    spec,runtime,binding,plan,history,grant,source=approved_entry(root,'mac',attempt,
        private_prefixes=private_prefixes,cleanup_only=cleanup_only)
    guard=readable_scope(root,spec,runtime,plan,source,embedded=embedded,cleanup_only=cleanup_only)
    original=guard
    def complete(*,cleanup_only=cleanup_only):
        value=original(cleanup_only=cleanup_only);verify_audit_tokenizer(plan['model_assets']);return value
    complete();return spec,runtime,binding,plan,history,grant,complete
