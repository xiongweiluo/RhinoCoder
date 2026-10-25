"""Fixed recovery candidate identity. Inert; no owner approval or field effects."""
from .c5_followup_profile import PYTHON,GPU_FLAGS,MAC_FLAGS
STUDY='C5DEV-RECOVERY-20261013'
INSTANCE='reuse-dev-recovery-20261013'
SPEC='eval/c5/recovery-development-spec-20261013.json'
RUNTIME='eval/c5/recovery-runtime-freeze-20261013.json'
PLAN='eval/c5/recovery-environment-plan-20261013.json'
HISTORY='eval/c5/recovery-history-20261013.json'
ENTRY='tools/run_c5_recovery_gpu_entry.py'
MAC_ENTRY='tools/run_c5_recovery_mac_entry.py'
POLICY='c5-engineering-recovery-v3'

RECOVERY_POLICY={'all_attempts_disclosed': True, 'budget_reset_on_retry': False, 'confirmation_inputs_per_invocation': 3, 'formal_attempts_after_exposure_or_generation_intent': 1, 'owner_confirmation_before_loading': True, 'owner_wait_consumes_attempt': False, 'protocol': 'c5-engineering-recovery-v3', 'public_attempts_max': 3, 'quality_failure_automatic_retry': False, 'retired_a_to_d_reopening_allowed': False, 'signals_per_qualified_target': 1, 'unknown_cleanup': 'pause_for_reconciliation'}
