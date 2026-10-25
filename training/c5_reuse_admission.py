"""Explicit legacy/D admission selection. No implicit initialization."""
from plugin.rhino_listener.c5_reuse_admission import AdmissionRegistry as LegacyAdmissionRegistry,ROLES,TABLE,valid
def AdmissionRegistry(binding,*,create=False):
    if binding.get('study_id')=='C5DEV-REUSE-20261012-D':
        from plugin.rhino_listener.c5_followup_admission import AdmissionRegistry as FollowupAdmissionRegistry
        return FollowupAdmissionRegistry(binding,create=create)
    return LegacyAdmissionRegistry(binding,create=create)
